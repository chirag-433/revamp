from django.core.management.base import BaseCommand

from complaints.services.matching import resolve_unmatched_cases
from complaints.services.overlap import run_full_overlap_scan, sync_conflict_suggestions


class Command(BaseCommand):
    help = "Run institution matching on unmatched cases and detect cross-bureau overlaps."

    def handle(self, *args, **options):
        self.stdout.write("Resolving unmatched cases...")
        match_stats = resolve_unmatched_cases()
        self.stdout.write(
            f"  Auto-resolved: {match_stats['resolved_auto']}, "
            f"Suggested for review: {match_stats['suggested_review']}, "
            f"Still unmatched: {match_stats['still_unmatched']}"
        )

        self.stdout.write("Running overlap detection...")
        overlap_stats = run_full_overlap_scan()
        self.stdout.write(
            f"  Institutions scanned: {overlap_stats['institutions_scanned']}, "
            f"Links created: {overlap_stats['links_created']}"
        )

        conflict_links = sync_conflict_suggestions()
        self.stdout.write(f"  Contradictory-action suggestions created: {len(conflict_links)}")

        self.stdout.write(self.style.SUCCESS("Matching and overlap scan complete."))
