from django.core.management.base import BaseCommand

from complaints.services.sla import refresh_sla_alerts


class Command(BaseCommand):
    help = "Refresh active in-app alerts for upcoming and missed case deadlines."

    def handle(self, *args, **options):
        counts = refresh_sla_alerts()
        self.stdout.write(self.style.SUCCESS(
            f"SLA alert queue refreshed: {counts['due_soon']} due soon, {counts['overdue']} overdue."
        ))
