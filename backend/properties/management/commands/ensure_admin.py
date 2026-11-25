"""Create the admin login, or reset its password, from environment variables.

Runs on every start (see start.sh), so on hosts without a shell (e.g. Render free plan)
you change the password by editing DEMO_PASSWORD in the dashboard and redeploying.

    ADMIN_USERNAME  default "ops"
    DEMO_PASSWORD   the password to set (skipped if empty)
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the admin user from ADMIN_USERNAME / DEMO_PASSWORD."

    def handle(self, *args, **opts):
        username = os.getenv("ADMIN_USERNAME", "ops")
        password = os.getenv("DEMO_PASSWORD", "")
        if not password:
            self.stdout.write("DEMO_PASSWORD not set; admin password left unchanged.")
            return
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username, defaults={"email": f"{username}@example.com", "first_name": "Operations"})
        user.is_staff = user.is_superuser = user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin '{username}' {'created' if created else 'password updated'}."))
