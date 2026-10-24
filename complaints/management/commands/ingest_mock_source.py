import csv
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from complaints.adapters import ADAPTERS
from complaints.services.csv_import import ALLOWED_COLUMNS, import_cases_csv


class Command(BaseCommand):
    help = "Ingest one synthetic RB or PGRC adapter fixture through the normal importer."

    def add_arguments(self, parser):
        parser.add_argument("source", choices=sorted(ADAPTERS))

    def handle(self, *args, **options):
        adapter = ADAPTERS[options["source"]]()
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=sorted(ALLOWED_COLUMNS))
        writer.writeheader()
        writer.writerows(adapter.canonical_rows())
        payload = stream.getvalue().encode("utf-8")
        try:
            result = import_cases_csv(SimpleUploadedFile("mock-source.csv", payload))
        except Exception as exc:
            raise CommandError(f"Mock {options['source'].upper()} import failed: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(
            f"{adapter.source_system}: {result.created} created, {result.updated} updated, "
            f"{len(result.errors)} row errors. Synthetic fixture only."
        ))
        for error in result.errors:
            self.stderr.write(error)
