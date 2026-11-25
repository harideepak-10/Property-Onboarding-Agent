"""Daily checks: licence renewal reminders and building follow-ups.

Schedule once a day, e.g. Windows Task Scheduler, cron, or a Render cron job:
    python manage.py run_agent_sweeps
"""
from django.core.management.base import BaseCommand

from agents.compliance import run_sweeps


class Command(BaseCommand):
    help = "Run the daily agent checks (licence reminders, building follow-ups)."

    def handle(self, *args, **opts):
        run = run_sweeps()
        for step in run.trace:
            self.stdout.write(f"- {step['label']}: {step['detail']}")
