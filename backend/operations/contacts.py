"""CSV import for building management contacts and vendors (export the client's sheet as CSV)."""
import csv
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Vendor

KIND_ALIASES = {"handyman": "handyman", "inspector": "handyman", "inspection": "handyman", "photographer": "photographer",
                "photo": "photographer", "photos": "photographer", "cleaner": "cleaner", "cleaning": "cleaner",
                "mover": "mover", "movers": "mover", "assembly": "mover"}


def _rows(fileobj):
    reader = csv.DictReader(fileobj)
    reader.fieldnames = [(f or "").strip().lower().replace(" ", "_") for f in (reader.fieldnames or [])]
    return reader


@transaction.atomic
def import_buildings(fileobj):
    """Columns: street_number, street_name, name, management_company, management_email, management_phone, notes"""
    from agents.models import Building
    from properties.models import Property
    created = updated = 0
    errors = []
    for n, row in enumerate(_rows(fileobj), start=2):
        num, street = (row.get("street_number") or "").strip(), (row.get("street_name") or "").strip()
        if not num or not street:
            errors.append(f"Row {n}: street number and street name are required.")
            continue
        b, was_new = Building.objects.update_or_create(street_number=num, street_name=street, defaults={
            k: (row.get(src) or "").strip() for k, src in [("name", "name"), ("management_company", "management_company"),
                                                          ("management_email", "management_email"), ("management_phone", "management_phone"),
                                                          ("registration_notes", "notes")] if (row.get(src) or "").strip()})
        created += was_new
        updated += not was_new
        for p in Property.objects.filter(building__isnull=True, street_number=num):
            if Building.match(p.street_number, p.street_name) == b:
                p.building = b
                p.save(update_fields=["building"])
    if errors:
        transaction.set_rollback(True)
        return {"created": 0, "updated": 0, "errors": errors}
    return {"created": created, "updated": updated, "errors": []}


@transaction.atomic
def import_vendors(fileobj):
    """Columns: name, kind (handyman/photographer/cleaner/mover/other), company, email, phone, rate, notes"""
    created = updated = 0
    errors = []
    for n, row in enumerate(_rows(fileobj), start=2):
        name = (row.get("name") or "").strip()
        if not name:
            errors.append(f"Row {n}: name is required.")
            continue
        rate = (row.get("rate") or "").replace("$", "").replace(",", "").strip()
        try:
            rate = Decimal(rate) if rate else None
        except InvalidOperation:
            errors.append(f"Row {n}: bad rate '{row.get('rate')}'.")
            continue
        email = (row.get("email") or "").strip()
        lookup = {"email__iexact": email} if email else {"name__iexact": name}
        v = Vendor.objects.filter(**lookup).first()
        was_new = v is None
        v = v or Vendor(name=name)
        v.name = name
        v.kind = KIND_ALIASES.get((row.get("kind") or "").strip().lower(), "other")
        for f in ("company", "phone", "notes"):
            if (row.get(f) or "").strip():
                setattr(v, f, row[f].strip())
        v.email, v.rate = email or v.email, rate if rate is not None else v.rate
        v.save()
        created += was_new
        updated += not was_new
    if errors:
        transaction.set_rollback(True)
        return {"created": 0, "updated": 0, "errors": errors}
    return {"created": created, "updated": updated, "errors": []}
