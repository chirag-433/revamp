from django.core.management.base import BaseCommand, CommandError

from complaints.models import ComplaintCase


class Command(BaseCommand):
    help = "Remove only synthetic DEMO and BENCHMARK cases so the demo can be reseeded."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true", help="Confirm removal of synthetic demo cases.")

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("No data was removed. Re-run with --confirm to remove DEMO/BENCHMARK cases.")
        cases = ComplaintCase.objects.filter(source_system__in=["DEMO", "BENCHMARK"])
        count = cases.count()
        cases.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Removed {count} synthetic cases. Institution reference records were kept."
        ))
