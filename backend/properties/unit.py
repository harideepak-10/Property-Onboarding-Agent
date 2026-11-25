"""Step 2 details: bedrooms and beds, keys/fobs/parking, utilities. Saving ticks step 2 tasks when complete."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from onboarding.engine import complete_by_title
from onboarding.models import PropertyStep, PropertyTask

from .models import Bedroom, UnitAccess, UtilityAccount
from .services import log

ADMIN_STEP = 2
ACCESS_FIELDS = ["keys_count", "fob_count", "fob_numbers", "mailbox_key", "keys_location", "registered_with_building",
                 "has_parking", "parking_spot", "parking_permit", "parking_registered", "locker", "notes"]
UTILITY_FIELDS = ["provider", "account_number", "status", "active_from", "monthly_cost", "notes"]


def access_for(prop):
    acc, _ = UnitAccess.objects.get_or_create(property=prop)
    return acc


@transaction.atomic
def save_bedrooms(prop, rooms, sofa_beds=None, sleeps_override="keep", user=None):
    """Replace the bedroom list. Keeps Property.bedrooms/beds in sync so older code and Guesty stay right."""
    sizes = Bedroom.BedSize.values
    clean = []
    for i, r in enumerate(rooms):
        size = (r.get("bed_size") or settings.UNIT["DEFAULT_BED_SIZE"]).lower()
        if size not in sizes:
            raise ValidationError(f"Unknown bed size '{size}'. Use {', '.join(sizes)}.")
        beds = int(r.get("beds") or 0)
        if beds < 0 or beds > 6:
            raise ValidationError("Beds per room must be between 0 and 6.")
        clean.append(Bedroom(property=prop, name=(r.get("name") or f"Bedroom {i + 1}").strip()[:60], bed_size=size, beds=beds,
                             is_bedroom=r.get("is_bedroom", True) not in (False, "false", 0, "0"), order=i))
    prop.bedrooms_detail.all().delete()
    Bedroom.objects.bulk_create(clean)
    prop.bedrooms = sum(1 for r in clean if r.is_bedroom)
    prop.beds = sum(r.beds for r in clean)
    if sofa_beds is not None:
        prop.sofa_beds = max(0, int(sofa_beds))
    if sleeps_override != "keep":
        prop.sleeps_override = int(sleeps_override) if sleeps_override not in (None, "") else None
    prop.save(update_fields=["bedrooms", "beds", "sofa_beds", "sleeps_override", "updated_at"])
    lay = prop.layout()
    log(prop, f"Unit layout saved: {lay['bedrooms']} bedroom(s), {lay['beds']} bed(s)"
        + (f" + {lay['sofa_beds']} sofa bed(s)" if lay["sofa_beds"] else "") + f", sleeps {lay['sleeps']}", actor=_who(user), user=user)
    return lay


@transaction.atomic
def save_access(prop, data, user=None):
    acc = access_for(prop)
    for f in ACCESS_FIELDS:
        if f in data:
            setattr(acc, f, data[f])
    acc.save()
    # keep the free-text fields used by the building email in sync
    if acc.parking_spot and prop.parking != acc.parking_spot:
        prop.parking = acc.parking_spot
    if acc.locker and prop.locker != acc.locker:
        prop.locker = acc.locker
    prop.save(update_fields=["parking", "locker", "updated_at"])
    sync_admin_tasks(prop, user)
    return acc


@transaction.atomic
def save_utility(prop, kind, data, user=None):
    if kind not in UtilityAccount.Kind.values:
        raise ValidationError("Unknown utility.")
    u, _ = UtilityAccount.objects.get_or_create(property=prop, kind=kind)
    old = u.status
    for f in UTILITY_FIELDS:
        if f in data:
            v = data[f]
            setattr(u, f, None if v == "" and f in ("active_from", "monthly_cost") else v)
    if u.status not in UtilityAccount.Status.values:
        raise ValidationError("Unknown status.")
    u.save()
    if old != u.status:
        log(prop, f"{u.get_kind_display()}: {u.get_status_display().lower()}" + (f" ({u.provider})" if u.provider else ""), actor=_who(user), user=user)
    sync_admin_tasks(prop, user)
    return u


def admin_readiness(prop):
    """What still blocks each step 2 task. Empty list = ready to tick."""
    acc = access_for(prop)
    utils = {u.kind: u for u in prop.utilities.all()}
    ok = (UtilityAccount.Status.ACTIVE, UtilityAccount.Status.INCLUDED)
    required = [k for k in settings.UNIT["REQUIRED_UTILITIES"] if k != "internet"]
    keys = []
    if acc.keys_count < 1 and acc.fob_count < 1:
        keys.append("Record how many keys and fobs you have")
    if not acc.registered_with_building:
        keys.append("Confirm the fobs are registered with the building")
    parking = [] if not acc.has_parking or acc.parking_registered else ["Confirm parking is registered"]
    utilities = [f"{UtilityAccount.Kind(k).label} not active yet" for k in required if not (k in utils and utils[k].status in ok)]
    internet = [] if ("internet" in utils and utils["internet"].status in ok) else ["Internet not active yet"]
    return {"Keys and fobs registered": keys, "Parking registered": parking, "Utilities set up": utilities, "Internet set up": internet}


def sync_admin_tasks(prop, user=None):
    if not PropertyStep.objects.filter(property=prop, template__number=ADMIN_STEP).exclude(status=PropertyStep.Status.LOCKED).exists():
        return []
    ready = [t for t, missing in admin_readiness(prop).items() if not missing]
    open_titles = set(PropertyTask.objects.filter(step__property=prop, step__template__number=ADMIN_STEP,
                                                  template__title__in=ready, done=False).values_list("template__title", flat=True))
    if open_titles:
        complete_by_title(prop, ADMIN_STEP, list(open_titles), actor="Unit details", user=user)
    return sorted(open_titles)


def _who(user):
    return (user.get_full_name() or user.get_username()) if user and user.is_authenticated else "Team"
