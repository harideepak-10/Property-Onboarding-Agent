"""Property creation and listing-nickname rules."""
import re

from django.conf import settings
from django.db import transaction
from django.db.models import Max

from .models import ActivityLog, Licence, Property


def street_code(street_name: str) -> str:
    """First three letters of the street name, skipping a leading 'The' or 'St'."""
    cleaned = re.sub(r"^(the|st\.?)\s+", "", street_name.strip(), flags=re.I)
    letters = re.sub(r"[^A-Za-z]", "", cleaned)
    return letters[:3].upper()


def build_nickname(sequence: int, city_code: str, street_name: str, unit: str) -> str:
    """A<sequence>-<CITY>-<STREET><UNIT>, e.g. A37313-TOR-BAY617.

    Assumed format until the client confirms what each part means.
    """
    unit_digits = re.sub(r"\D", "", unit or "")
    return f"A{sequence}-{city_code.upper()}-{street_code(street_name)}{unit_digits}"


NICKNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.#/-]{0,39}$")


def clean_nickname(value, exclude_pk=None) -> str:
    """Any name or number the team likes (letters, numbers, spaces, - _ . # /), unique, up to 40 characters."""
    from django.core.exceptions import ValidationError
    nick = re.sub(r"\s+", " ", (value or "").strip())
    if not NICKNAME_RE.match(nick):
        raise ValidationError("Use up to 40 letters, numbers, spaces or - _ . # / for the nickname.")
    if Property.objects.filter(nickname__iexact=nick).exclude(pk=exclude_pk).exists():
        raise ValidationError(f"Another property is already called {nick}.")
    return nick


def next_sequence() -> int:
    start = settings.ONBOARDING["NICKNAME_START"]
    current = Property.objects.aggregate(m=Max("sequence"))["m"]
    return max(start, (current or 0) + 1)


def log(prop, message, actor="System", user=None):
    return ActivityLog.objects.create(property=prop, message=message, actor=actor, user=user)


@transaction.atomic
def create_property(data: dict, user=None) -> Property:
    """Create a property, its licence record and its 12-step onboarding checklist."""
    from onboarding.engine import create_checklist  # avoid circular import

    city_code = data.pop("city_code", None) or settings.ONBOARDING["DEFAULT_CITY_CODE"]
    sequence = data.pop("sequence", None) or next_sequence()
    custom = data.pop("nickname", "") or ""
    nickname = clean_nickname(custom) if custom.strip() else build_nickname(sequence, city_code, data["street_name"], data["unit"])
    prop = Property.objects.create(sequence=sequence, city_code=city_code, nickname=nickname, **data)
    Licence.objects.create(property=prop)
    create_checklist(prop)
    log(prop, f"Property created with nickname {nickname}", actor=user.get_full_name() or user.username if user else "System", user=user)
    return prop
