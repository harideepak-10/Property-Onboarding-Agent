"""Daily checks: licence renewal reminders, building and photographer follow-ups, and the digest.

Schedule once a day, e.g. Windows Task Scheduler, cron, or a Render cron job:
    python manage.py run_agent_sweeps --digest
"""
from django.core.management.base import BaseCommand

from agents.compliance import run_sweeps


class Command(BaseCommand):
    help = "Run the daily agent checks (licence reminders, building and photographer follow-ups)."

    def add_arguments(self, parser):
        parser.add_argument("--digest", action="store_true", help="Also email (and Slack) the daily digest")

    def handle(self, *args, **opts):
        run = run_sweeps()
        for step in run.trace:
            self.stdout.write(f"- {step['label']}: {step['detail']}")
        if opts["digest"]:
            from operations.services import send_digest
            for n in send_digest():
                self.stdout.write(f"- Digest sent by {n.channel}{' (dry run)' if n.dry_run else ''}")
