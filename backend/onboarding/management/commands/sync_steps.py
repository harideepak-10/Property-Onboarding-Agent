from django.core.management.base import BaseCommand

from onboarding.definitions import sync_definitions
from onboarding.engine import create_checklist
from onboarding.models import StepTemplate, TaskTemplate
from properties.models import Property


class Command(BaseCommand):
    help = "Sync the 12-step onboarding definitions and add any new tasks to existing properties."

    def handle(self, *args, **opts):
        sync_definitions(StepTemplate, TaskTemplate)
        for prop in Property.objects.all():
            create_checklist(prop)
        self.stdout.write(self.style.SUCCESS(f"Synced {StepTemplate.objects.count()} steps."))
