"""Photos, listing profile, readiness and the Listing agent."""
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from agents.integrations.google_workspace import GoogleWorkspace
from agents.models import AgentRun, EmailDraft
from onboarding.engine import complete_by_title
from onboarding.models import PropertyStep, PropertyTask
from properties.services import log

from .guesty import Guesty, GuestyError, listing_payload
from .models import ListingProfile, Photo, PhotoSet

AGENT = "Listing agent"
DEFAULT_AMENITIES = ["Wifi", "Kitchen", "Washer", "Dryer", "Air conditioning", "Heating", "TV", "Essentials",
                     "Hair dryer", "Iron", "Hangers", "Smoke detector", "Carbon monoxide detector", "Fire extinguisher",
                     "First aid kit", "Laptop friendly workspace", "Self check-in"]
ROOM_WORDS = [("living", "Living room"), ("lounge", "Living room"), ("bed", "Bedroom"), ("kitchen", "Kitchen"),
              ("bath", "Bathroom"), ("wash", "Bathroom"), ("dining", "Dining area"), ("view", "View"),
              ("balcony", "Balcony"), ("exterior", "Building"), ("building", "Building"), ("lobby", "Building"),
              ("gym", "Amenity"), ("pool", "Amenity")]
ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 20 * 1024 * 1024


def profile(prop) -> ListingProfile:
    p, _ = ListingProfile.objects.get_or_create(property=prop, defaults={
        "accommodates": max(1, prop.beds * 2), "amenities": DEFAULT_AMENITIES})
    return p


def current_set(prop):
    return prop.photo_sets.filter(is_current=True).prefetch_related("photos").first()


def guess_room(name):
    n = name.lower()
    return next((room for word, room in ROOM_WORDS if word in n), "")


def _new_set(prop, kind, source, user=None, drive_url=""):
    prop.photo_sets.update(is_current=False)
    return PhotoSet.objects.create(property=prop, kind=kind, source=source, drive_url=drive_url, created_by=user)


def _add(photo_set, name, data):
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED:
        raise ValidationError(f"{name}: only JPG, PNG or WebP photos.")
    if len(data) > MAX_BYTES:
        raise ValidationError(f"{name} is over 20 MB.")
    try:
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(data)) as im:
            width, height = im.size
    except Exception:  # noqa: BLE001
        raise ValidationError(f"{name} isn't a readable image.")
    order = (photo_set.photos.aggregate(m=Max("order"))["m"] or 0) + 1
    room = guess_room(name)
    # Store the size up front so loading a photo never has to open the file
    photo = Photo(photo_set=photo_set, original_name=name, room=room, caption=room, order=order,
                  width=width, height=height, is_cover=not photo_set.photos.filter(is_cover=True).exists())
    photo.image.save(name, ContentFile(data), save=False)
    photo.width, photo.height = width, height  # saving the file can reset these; set them last
    photo.save()
    return photo


@transaction.atomic
def add_photos(prop, files, kind=PhotoSet.Kind.SHOOT, new_set=False, user=None):
    """files: iterable of (name, bytes). Starts a new set for a re-shoot, otherwise adds to the current one."""
    files = list(files)
    if not files:
        raise ValidationError("Choose at least one photo.")
    cur = current_set(prop)
    ps = _new_set(prop, kind, PhotoSet.Source.UPLOAD, user) if (new_set or not cur) else cur
    for name, data in files:
        _add(ps, name, data)
    log(prop, f"Added {len(files)} photo(s) to the {ps.get_kind_display().lower()}", actor=_who(user), user=user)
    return ps


@transaction.atomic
def import_from_drive(prop, url, kind=PhotoSet.Kind.SHOOT, user=None, google=None):
    google = google or GoogleWorkspace()
    folder = google.folder_id_from_url(url)
    if not folder:
        raise ValidationError("That doesn't look like a Google Drive folder link.")
    listing = google.list_images(folder)
    if listing.dry_run:
        raise ValidationError("Google Drive isn't connected yet (dry-run mode). Download the photos and upload them here instead.")
    if not listing["files"]:
        raise ValidationError("No photos found in that Drive folder. Check it's shared with the service account.")
    ps = _new_set(prop, kind, PhotoSet.Source.DRIVE, user, drive_url=url)
    for f in listing["files"]:
        p = _add(ps, f["name"], google.download(f["id"]))
        p.drive_file_id = f["id"]
        p.save(update_fields=["drive_file_id"])
    log(prop, f"Imported {len(listing['files'])} photos from the photographer's Drive folder", actor=_who(user), user=user)
    return ps


def set_cover(photo):
    Photo.objects.filter(photo_set=photo.photo_set).update(is_cover=False)
    photo.is_cover = True
    photo.save(update_fields=["is_cover"])


def reorder(photo_set, ids):
    for i, pid in enumerate(ids, start=1):
        Photo.objects.filter(photo_set=photo_set, pk=pid).update(order=i)


def ordered(photo_set):
    return list(photo_set.photos.all()) if photo_set else []  # Meta ordering: cover first, then order


def _who(user):
    return (user.get_full_name() or user.get_username()) if user else "Team"


# ---------- readiness ----------

def _task(prop, step, title):
    return PropertyTask.objects.filter(step__property=prop, step__template__number=step, template__title=title, done=True).exists()


def readiness(prop):
    ps = current_set(prop)
    n = ps.photos.count() if ps else 0
    minimum = settings.LISTINGS["MIN_PHOTOS"]
    pro = bool(ps and ps.kind != PhotoSet.Kind.INSPECTION)
    checks = [
        ("Professional photos received", pro),
        (f"At least {minimum} photos ({n})", n >= minimum),
        ("Cover photo chosen", bool(ps and ps.photos.filter(is_cover=True).exists())),
        ("Listing created in Guesty", bool(prop.guesty_listing_id)),
        ("Photos uploaded to Guesty", bool(ps and ps.uploaded_to_guesty_at)),
        ("Angel Host notified", _task(prop, 10, "Angel Host emailed: ready to optimize")),
        ("Titles, descriptions and pricing optimized (Angel Host)", _task(prop, 10, "Optimization confirmed")),
        ("STR licence approved (number shown on the listing)", prop.licence.status == "approved"),
        ("Guidebook, lockbox and buzzer set up", PropertyStep.objects.filter(property=prop, template__number=11, status="done").exists()),
    ]
    done = sum(1 for _, ok in checks if ok)
    return {"checks": [{"label": l, "ok": ok} for l, ok in checks], "pct": round(100 * done / len(checks))}


def channels(prop):
    return [{"name": n, "live": _task(prop, 12, t)} for n, t in
            [("Airbnb", "Live on Airbnb"), ("Booking.com", "Live on Booking.com"), ("Direct-booking site", "Live on direct-booking site")]]


# ---------- Listing agent ----------

def _tick(prop, step, titles, user, note=""):
    try:
        complete_by_title(prop, step, titles, actor=AGENT, user=user, proof_note=note)
        return True
    except ValidationError:
        return False


def angel_host_draft(prop, prof, ps, reshoot=False):
    to = settings.LISTINGS["ANGEL_HOST_EMAIL"]
    intro = ("We've uploaded a new photo set (re-shoot) to this listing. Please update the photo order, cover and photo tour."
             if reshoot else "This listing is built in Guesty and the photos are uploaded. It's ready for you to optimize.")
    body = f"""Hi Angel Host team,

{intro}

Listing: {prop.nickname}
Guesty ID: {prop.guesty_listing_id}
Address: {prop.address}, {prop.city}
Size: {prop.bedrooms} bedroom(s), {prop.bathrooms} bathroom(s), {prop.beds} bed(s), sleeps {prof.effective_accommodates()}
Photos: {ps.photos.count()} ({ps.get_kind_display().lower()})
Working title: {prof.effective_title()}
{f'Notes: {prop.special_terms}' + chr(10) if prop.special_terms else ''}
Please handle the photo order, cover photo, photo tour, titles, descriptions and pricing, and reply when it's done.

Thank you,
Operations team
{settings.AGENTS['OPS_EMAIL']}
"""
    return EmailDraft.objects.create(
        property=prop, kind=EmailDraft.Kind.ANGEL_HOST, to=to,
        subject=f"{'Updated photos' if reshoot else 'Ready to optimize'}: {prop.nickname}", body=body,
        warning="" if to else "Add ANGEL_HOST_EMAIL in settings, or type their address here.", created_by_agent=AGENT)


def run_listing(prop, user=None, guesty=None) -> AgentRun:
    guesty = guesty or Guesty()
    run = AgentRun.objects.create(agent=AgentRun.Agent.LISTING, property=prop, started_by=user)
    warnings = 0
    try:
        prof = profile(prop)
        ps = current_set(prop)
        minimum = settings.LISTINGS["MIN_PHOTOS"]
        n = ps.photos.count() if ps else 0

        # 1. Photos received
        if n < minimum:
            run.add("Waiting for photos", "warn", f"{n} photo(s) on file; at least {minimum} are needed. Upload the photographer's set first.")
            run.status, run.finished_at = AgentRun.Status.PARTIAL, timezone.now()
            run.save()
            return run
        note = ps.drive_url or f"{n} photos uploaded on {ps.received_at:%Y-%m-%d}"
        if ps.kind != PhotoSet.Kind.INSPECTION:
            _tick(prop, 8, ["Shoot booked"], user)
            ok = _tick(prop, 8, ["Photos received (Drive link)"], user, note)
            run.add("Checked the photo set", "ok" if ok else "warn",
                    f"{n} photos · {ps.get_kind_display()}" + ("" if ok else " · step 8 unlocks after setup day (step 7)"))
            warnings += not ok
        else:
            run.add("Only inspection photos on file", "warn", "Upload the professional shoot before building the listing.")
            warnings += 1

        step9 = PropertyStep.objects.get(property=prop, template__number=9)
        if step9.status == PropertyStep.Status.LOCKED:
            run.add("Listing not built yet", "warn", "Step 9 unlocks when the photos step (8) is complete.")
            run.status, run.finished_at = AgentRun.Status.PARTIAL, timezone.now()
            run.save()
            return run

        # 2. Create the Guesty listing
        if not prop.guesty_listing_id:
            res = guesty.create_listing(listing_payload(prop, prof))
            prop.guesty_listing_id = res["_id"]
            prop.save(update_fields=["guesty_listing_id"])
            prof.guesty_status, prof.guesty_dry_run = ListingProfile.GuestyStatus.CREATED, res.dry_run
            prof.save(update_fields=["guesty_status", "guesty_dry_run"])
            _tick(prop, 9, ["Listing created with nickname"], user, f"Guesty ID {res['_id']}")
            run.add("Created the listing in Guesty", detail=f"{prop.nickname} · hidden from marketplaces until go-live", dry_run=res.dry_run)
        else:
            _tick(prop, 9, ["Listing created with nickname"], user, f"Guesty ID {prop.guesty_listing_id}")
            run.add("Guesty listing already exists", "skip", prop.guesty_listing_id)

        # 3. Upload photos (replace the set on a re-shoot)
        if ps.uploaded_to_guesty_at:
            run.add("Photos already uploaded", "skip", f"Uploaded {ps.uploaded_to_guesty_at:%Y-%m-%d}")
        else:
            photos = ordered(ps)
            payload = [{"url": p.public_url(), "caption": p.caption or p.room} for p in photos]
            if guesty.live and not settings.LISTINGS["PUBLIC_BASE_URL"]:
                run.add("Couldn't upload photos", "warn", "Set PUBLIC_BASE_URL so Guesty can download the photos (it can't reach localhost).")
                warnings += 1
            else:
                replacing = prop.photo_sets.exclude(pk=ps.pk).filter(uploaded_to_guesty_at__isnull=False).exists()
                res = (guesty.replace_photos if replacing else guesty.add_photos)(prop.guesty_listing_id, payload)
                ps.uploaded_to_guesty_at = timezone.now()
                ps.save(update_fields=["uploaded_to_guesty_at"])
                prof.guesty_status, prof.guesty_synced_at = ListingProfile.GuestyStatus.PHOTOS_UPLOADED, timezone.now()
                prof.save(update_fields=["guesty_status", "guesty_synced_at"])
                _tick(prop, 9, ["Photos uploaded to Guesty"], user, f"{len(payload)} photos")
                run.add("Replaced the photos in Guesty" if replacing else "Uploaded the photos to Guesty",
                        detail=f"{len(payload)} photos, cover first", dry_run=res.dry_run)

                # 4. Tell Angel Host
                draft = angel_host_draft(prop, prof, ps, reshoot=replacing)
                run.add("Drafted the email to Angel Host", "warn" if draft.warning else "ok",
                        draft.warning or f"To {draft.to} · waiting for your approval")
                warnings += bool(draft.warning)

        log(prop, "Listing agent finished", actor=AGENT, user=user)
        run.status = AgentRun.Status.PARTIAL if warnings else AgentRun.Status.SUCCEEDED
    except GuestyError as e:
        run.add("Guesty returned an error", "error", str(e))
        run.status, run.error = AgentRun.Status.FAILED, str(e)
    except Exception as e:  # noqa: BLE001
        run.add("Stopped because of an error", "error", f"{type(e).__name__}: {e}")
        run.status, run.error = AgentRun.Status.FAILED, str(e)
    run.finished_at = timezone.now()
    run.save()
    return run
