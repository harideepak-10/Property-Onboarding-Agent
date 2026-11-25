from django.db import migrations

STORES = [
    ("amazon", "Amazon", "https://www.amazon.ca/s?k={q}", "#232f3e"),
    ("walmart", "Walmart", "https://www.walmart.ca/search?q={q}", "#0071dc"),
    ("ikea", "IKEA", "https://www.ikea.com/ca/en/search/?q={q}", "#0058a3"),
    ("costco", "Costco", "https://www.costco.ca/CatalogSearch?keyword={q}", "#d9232e"),
    ("homedepot", "Home Depot", "https://www.homedepot.ca/search?q={q}", "#f26b1d"),
    ("wayfair", "Wayfair", "https://www.wayfair.ca/keyword.php?keyword={q}", "#7b189f"),
    ("homesense", "HomeSense", "", "#6b4f8a"),
]


def seed(apps, schema_editor):
    Store = apps.get_model("procurement", "Store")
    for code, name, url, color in STORES:
        Store.objects.update_or_create(code=code, defaults={"name": name, "search_url": url, "color": color})


class Migration(migrations.Migration):
    dependencies = [("procurement", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
