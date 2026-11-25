from django.db import migrations


def seed(apps, schema_editor):
    from onboarding.definitions import sync_definitions
    sync_definitions(apps.get_model("onboarding", "StepTemplate"), apps.get_model("onboarding", "TaskTemplate"))


class Migration(migrations.Migration):
    dependencies = [("onboarding", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
