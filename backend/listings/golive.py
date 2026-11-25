"""Guest experience (step 11) and go-live (step 12)."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from agents.models import AgentRun
from onboarding.engine import complete_by_title
from onboarding.models import PropertyStep, PropertyTask
from properties.models import Licence
from properties.services import log

from .guesty import Guesty, GuestyError
from .models import GuestGuide
from .services import current_set, profile

AGENT = "Go-live agent"
MASK = "••••••"
CHANNEL_TASKS = {"airbnb": "Live on Airbnb", "booking": "Live on Booking.com", "direct": "Live on direct-booking site"}


def _who(user):
    return (user.get_full_name() or user.get_username()) if user else "Team"


def _tick(prop, step, titles, user, note=""):
    try:
        complete_by_title(prop, step, titles, actor=_who(user), user=user, proof_note=note)
        return True
    except ValidationError:
        return False


# ---------- guest guide ----------

def guide(prop) -> GuestGuide:
    g, _ = GuestGuide.objects.get_or_create(property=prop, defaults={
        "parking_instructions": f"Parking spot {prop.parking}" if prop.parking else ""})
    return g


@transaction.atomic
def update_guide(prop, data: dict, user=None):
    g = guide(prop)
    editable = [f.name for f in GuestGuide._meta.fields if f.name not in ("id", "property", "updated_at")]
    changed = []
    for k, v in data.items():
        if k not in editable or (k in GuestGuide.SECRET_FIELDS and v == MASK):
            continue
        if getattr(g, k) != v:
            setattr(g, k, v)
            changed.append(k)
    g.save()
    if changed:
        shown = [c.replace("_", " ") for c in changed if c not in GuestGuide.SECRET_FIELDS]
        hidden = [c.replace("_", " ") for c in changed if c in GuestGuide.SECRET_FIELDS]
        log(prop, "Guest guide updated: " + ", ".join(shown + [f"{h} (hidden)" for h in hidden]), actor=_who(user), user=user)
    notes = sync_step_11(prop, g, user)
    return g, notes


def sync_step_11(prop, g, user=None):
    """Tick step 11 tasks the guide now proves. Returns notes for anything that couldn't be ticked."""
    notes = []
    want = []
    if g.lockbox_location and g.lockbox_code:
        want.append(("Lockbox code set", f"Lockbox: {g.lockbox_location}"))
    if g.buzzer_instructions:
        want.append(("Building buzzer access set", "Buzzer instructions in the guest guide"))
    if g.enso_guidebook_url and not g.missing():
        want.append(("Enso Connect guidebook set up", g.enso_guidebook_url))
    for title, note in want:
        if not _tick(prop, 11, [title], user, note):
            notes.append("Step 11 unlocks after setup day (step 7); the guide is saved and will count then.")
            break
    return notes


def reveal(prop, user=None):
    g = guide(prop)
    log(prop, "Viewed the guest access codes", actor=_who(user), user=user)
    return {"lockbox_code": g.lockbox_code, "wifi_password": g.wifi_password, "guidebook_text": guidebook_text(prop, g)}


def guidebook_text(prop, g=None):
    """Plain-text guidebook, ready to paste into Enso Connect section by section."""
    g = g or guide(prop)
    lp = profile(prop)
    sections = [
        ("Welcome", f"Welcome to {lp.effective_title()}! {prop.address}, {prop.city}."),
        ("Check-in and check-out", f"Check-in from {g.check_in_time}. Check-out by {g.check_out_time}."),
        ("Getting in", g.arrival_instructions),
        ("Building buzzer", g.buzzer_instructions),
        ("Lockbox", f"{g.lockbox_location}\nCode: {g.lockbox_code}" if g.lockbox_location else ""),
        ("Wi-Fi", f"Network: {g.wifi_name}\nPassword: {g.wifi_password}" if g.wifi_name else ""),
        ("Parking", g.parking_instructions),
        ("Garbage and recycling", g.garbage_instructions),
        ("House rules", g.house_rules),
        ("Local tips", g.local_tips),
        ("Need help?", g.emergency_contact),
    ]
    return "\n\n".join(f"{title}\n{body.strip()}" for title, body in sections if body and body.strip())


# ---------- go-live ----------

def preflight(prop):
    lp = profile(prop)
    steps = list(PropertyStep.objects.filter(property=prop, template__number__lte=11).select_related("template"))
    open_steps = [f"{s.template.number}. {s.template.name}" for s in steps if s.status != "done"]
    lic = prop.licence
    days = (lic.expires_on - timezone.localdate()).days if lic.expires_on else None
    ps = current_set(prop)
    g = guide(prop)
    checks = [
        ("Steps 1–11 complete", not open_steps, True, "Open: " + ", ".join(open_steps) if open_steps else ""),
        ("STR licence approved with a number", lic.status == Licence.Status.APPROVED and bool(lic.number), True,
         lic.get_status_display() if lic.status != Licence.Status.APPROVED else ("" if lic.number else "Add the licence number")),
        ("Licence valid for at least 30 more days", days is not None and days >= 30, False,
         f"Expires in {days} days" if days is not None else "No expiry date recorded"),
        ("Listing created in Guesty", bool(prop.guesty_listing_id), True, ""),
        ("Photos uploaded to Guesty", bool(ps and ps.uploaded_to_guesty_at), True, ""),
        ("Guest guide complete", not g.missing(), True, ("Missing: " + ", ".join(g.missing())) if g.missing() else ""),
        ("Enso Connect guidebook linked", bool(g.enso_guidebook_url), True, ""),
    ]
    out = [{"label": l, "ok": ok, "blocking": b, "detail": d} for l, ok, b, d in checks]
    return {"checks": out, "ready": all(c["ok"] for c in out if c["blocking"]), "is_listed": lp.is_listed,
            "listed_at": lp.listed_at, "dry_run": lp.guesty_dry_run or not Guesty().live}


@transaction.atomic
def approve(prop, user=None, guesty=None):
    pf = preflight(prop)
    if not pf["ready"]:
        failing = [c["label"] for c in pf["checks"] if c["blocking"] and not c["ok"]]
        raise ValidationError("Not ready to go live: " + "; ".join(failing))
    guesty = guesty or Guesty()
    run = AgentRun.objects.create(agent=AgentRun.Agent.GO_LIVE, property=prop, started_by=user)
    run.add("Final check passed", detail=f"Approved by {_who(user)}")
    _tick(prop, 12, ["Final check passed"], user, f"Approved by {_who(user)}")
    try:
        res = guesty.set_listed(prop.guesty_listing_id, True)
    except GuestyError as e:
        run.add("Guesty didn't list the property", "error", str(e))
        run.status, run.error, run.finished_at = AgentRun.Status.FAILED, str(e), timezone.now()
        run.save()
        return run
    lp = profile(prop)
    lp.is_listed, lp.listed_at = True, timezone.now()
    lp.save(update_fields=["is_listed", "listed_at"])
    run.add("Listed the property on its connected channels", detail="Guesty isListed = true", dry_run=res.dry_run)
    run.add("Confirm each channel", "warn", "Open Airbnb, Booking.com and the direct site, then mark each one live here.")
    log(prop, "Approved go-live and listed the property in Guesty", actor=_who(user), user=user)
    run.status, run.finished_at = AgentRun.Status.PARTIAL, timezone.now()
    run.save()
    return run


def confirm_channel(prop, channel, user=None):
    title = CHANNEL_TASKS.get(channel)
    if not title:
        raise ValidationError("Unknown channel.")
    if not profile(prop).is_listed:
        raise ValidationError("Approve go-live first.")
    if not _tick(prop, 12, [title], user, "Checked the live listing"):
        raise ValidationError("Step 12 is locked. Finish the earlier steps first.")


@transaction.atomic
def unlist(prop, reason, user=None, guesty=None):
    lp = profile(prop)
    if not lp.is_listed:
        raise ValidationError("This property isn't listed.")
    res = (guesty or Guesty()).set_listed(prop.guesty_listing_id, False)
    lp.is_listed = False
    lp.save(update_fields=["is_listed"])
    PropertyTask.objects.filter(step__property=prop, step__template__number=12,
                                template__title__in=list(CHANNEL_TASKS.values())).update(done=False, done_at=None)
    from onboarding.engine import refresh_statuses
    refresh_statuses(prop)
    log(prop, f"{'Dry run: would have unlisted' if res.dry_run else 'Unlisted'} the property. Reason: {reason or 'not given'}",
        actor=_who(user), user=user)
