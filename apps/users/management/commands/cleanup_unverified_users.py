# apps/users/management/commands/cleanup_unverified_users.py
#
# SETUP INSTRUCTIONS:
# 1. Create folder: apps/users/management/
# 2. Create file:   apps/users/management/__init__.py  (empty file)
# 3. Create folder: apps/users/management/commands/
# 4. Create file:   apps/users/management/commands/__init__.py  (empty file)
# 5. Copy this file to: apps/users/management/commands/cleanup_unverified_users.py
#
# HOW TO RUN MANUALLY:
#   python manage.py cleanup_unverified_users
#
# HOW TO RUN AUTOMATICALLY (add to settings.py with django-crontab):
#   CRONJOBS = [
#       ('0 2 * * *', 'django.core.management.call_command', ['cleanup_unverified_users']),
#   ]
#   This runs every day at 2:00 AM automatically.
#
# OR run via Render cron job (recommended for your deployment):
#   In Render dashboard → Cron Jobs → Add:
#   Command: python manage.py cleanup_unverified_users
#   Schedule: 0 2 * * *  (daily at 2 AM)

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete unverified user accounts older than 24 hours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Delete unverified accounts older than this many hours (default: 24)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        hours    = options['hours']
        dry_run  = options['dry_run']
        cutoff   = timezone.now() - timedelta(hours=hours)

        # Find unverified accounts older than cutoff
        # Exclude superusers and staff for safety
        old_unverified = User.objects.filter(
            is_verified  = False,
            is_staff     = False,
            is_superuser = False,
            date_joined__lt = cutoff,
        )

        count = old_unverified.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS(
                f'No unverified accounts older than {hours} hours found.'
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN — Would delete {count} unverified accounts:'
            ))
            for user in old_unverified[:20]:  # show max 20
                self.stdout.write(f'  - {user.email} (joined: {user.date_joined})')
            if count > 20:
                self.stdout.write(f'  ... and {count - 20} more')
            return

        # Log before deleting
        emails = list(old_unverified.values_list('email', flat=True)[:50])
        logger.info(
            "Deleting %d unverified accounts older than %d hours: %s",
            count, hours, emails[:10]
        )

        # Delete them
        deleted_count, _ = old_unverified.delete()

        self.stdout.write(self.style.SUCCESS(
            f'Successfully deleted {deleted_count} unverified accounts older than {hours} hours.'
        ))
        logger.info("Cleanup complete — deleted %d unverified accounts", deleted_count)