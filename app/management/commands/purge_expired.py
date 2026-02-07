"""
Django management command to purge expired documents and workspaces.

Documents and workspaces expire after 30 days of inactivity (no read or write).
This command should be run on a cron schedule (e.g., daily).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from app.models import Document, Workspace


class Command(BaseCommand):
    help = "Purge documents and workspaces that have not been accessed for 30 days"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Number of days of inactivity before purging (default: 30)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        cutoff = timezone.now() - timedelta(days=days)

        # Find and delete expired documents
        expired_docs = Document.objects.filter(last_accessed__lt=cutoff)
        docs_deleted, _ = expired_docs.delete()

        # Find and delete expired workspaces
        expired_workspaces = Workspace.objects.filter(last_accessed__lt=cutoff)
        ws_deleted, _ = expired_workspaces.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully purged {docs_deleted} expired documents and "
                f"{ws_deleted} expired workspaces "
                f"(not accessed since {cutoff.strftime('%Y-%m-%d %H:%M:%S')})"
            )
        )
