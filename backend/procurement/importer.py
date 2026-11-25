"""Import the client's master supply list from CSV (export their Google Sheet as CSV).

Columns: category, name, item_type, store, typical_price, rule, multiplier,
product_url, store_sku, alt_name, alt_store, alt_price, alt_url
Rows are matched on (name, store) so re-importing updates prices and links.
"""
import csv
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import ItemAlternative, MasterItem, Store

RULE_ALIASES = {
    "fixed": "fixed", "one per unit": "fixed",
    "per bedroom": "per_bedroom", "per_bedroom": "per_bedroom",
    "per bathroom": "per_bathroom", "per_bathroom": "per_bathroom",
    "per bed": "per_bed", "per_bed": "per_bed",
}


class ImportErrorRow(Exception):
    pass


def _store(code):
    code = (code or "").strip().lower().replace(" ", "")
    try:
        return Store.objects.get(code=code)
    except Store.DoesNotExist:
        raise ImportErrorRow(f"unknown store '{code}'. Known: {', '.join(Store.objects.values_list('code', flat=True))}")


def _price(v):
    try:
        return Decimal(str(v).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ImportErrorRow(f"bad price '{v}'")


@transaction.atomic
def import_csv(fileobj, deactivate_missing=False):
    reader = csv.DictReader(fileobj)
    created = updated = 0
    errors, seen = [], set()
    for n, row in enumerate(reader, start=2):
        try:
            rule = RULE_ALIASES.get((row.get("rule") or "fixed").strip().lower())
            if not rule:
                raise ImportErrorRow(f"unknown quantity rule '{row.get('rule')}'")
            category = (row.get("category") or "").strip().lower()
            if category not in MasterItem.Category.values:
                raise ImportErrorRow(f"unknown category '{category}'")
            store = _store(row.get("store"))
            item, was_created = MasterItem.objects.update_or_create(
                name=row["name"].strip(), store=store,
                defaults={
                    "category": category,
                    "item_type": (row.get("item_type") or row["name"]).strip().lower(),
                    "typical_price": _price(row.get("typical_price")),
                    "rule": rule,
                    "multiplier": int(row.get("multiplier") or 1),
                    "product_url": (row.get("product_url") or "").strip(),
                    "store_sku": (row.get("store_sku") or "").strip(),
                    "is_active": True,
                },
            )
            seen.add(item.pk)
            created += was_created
            updated += not was_created
            if (row.get("alt_name") or "").strip():
                ItemAlternative.objects.update_or_create(
                    item=item, priority=1,
                    defaults={"name": row["alt_name"].strip(), "store": _store(row.get("alt_store") or row.get("store")),
                              "typical_price": _price(row.get("alt_price") or row.get("typical_price")),
                              "product_url": (row.get("alt_url") or "").strip()},
                )
        except (ImportErrorRow, KeyError, ValueError) as e:
            errors.append(f"Row {n}: {e}")
    if errors:
        transaction.set_rollback(True)
        return {"created": 0, "updated": 0, "errors": errors}
    if deactivate_missing:
        MasterItem.objects.exclude(pk__in=seen).update(is_active=False)
    return {"created": created, "updated": updated, "errors": []}
