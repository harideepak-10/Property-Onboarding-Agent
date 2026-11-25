"""Fill in width/height for photos saved without them, so loading a photo never opens its file."""
from django.db import migrations


def backfill(apps, schema_editor):
    from django.core.files.storage import default_storage
    from PIL import Image

    Photo = apps.get_model("listings", "Photo")
    for pk, name in Photo.objects.filter(width__isnull=True).values_list("pk", "image"):
        try:
            with default_storage.open(name) as fh, Image.open(fh) as im:
                w, h = im.size
        except Exception:  # noqa: BLE001 - file missing or unreadable: use a placeholder size
            w, h = 1, 1
        Photo.objects.filter(pk=pk).update(width=w, height=h)


class Migration(migrations.Migration):
    dependencies = [("listings", "0002_guest_guide_golive")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
