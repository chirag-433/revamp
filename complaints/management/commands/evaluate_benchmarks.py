import csv
import html
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from complaints.models import CaseLink, Institution, SyntheticLinkLabel, SyntheticMatchLabel
from complaints.services.matching import find_candidates


class Command(BaseCommand):
    help = "Evaluate institution matching and synthetic overlap/conflict labels."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="artifacts/evaluation")
        parser.add_argument("--dataset", default="demo-match-v1")
        parser.add_argument("--link-dataset", default="demo-links-v1")

    def handle(self, *args, **options):
        labels = list(SyntheticMatchLabel.objects.filter(
            dataset=options["dataset"]
        ).select_related("case", "expected_institution"))
        link_labels = list(SyntheticLinkLabel.objects.filter(
            dataset=options["link_dataset"]
        ).select_related("case_a", "case_b"))
        if not labels and not link_labels:
            raise CommandError("No synthetic benchmark labels exist. Run seed_demo and seed_match_benchmark first.")

        scored = []
        institutions = list(Institution.objects.filter(is_active=True).prefetch_related("aliases"))
        for label in labels:
            candidates = find_candidates(
                label.case.raw_institution_name, top_n=1, institutions=institutions
            )
            scored.append((label, candidates[0] if candidates else None))

        rows = []
        for step in range(20):
            threshold = round(0.60 + step * 0.02, 2)
            predicted = [
                (label, candidate)
                for label, candidate in scored
                if candidate and candidate.score >= threshold
            ]
            true_positives = sum(
                1 for label, candidate in predicted
                if label.expected_institution_id
                and candidate.institution.pk == label.expected_institution_id
            )
            expected = sum(1 for label, _ in scored if label.expected_institution_id)
            false_positives = len(predicted) - true_positives
            false_negatives = expected - true_positives
            rows.append({
                "metric": "institution_matching",
                "threshold": f"{threshold:.2f}",
                "precision_percent": round(100 * true_positives / len(predicted), 2) if predicted else "",
                "recall_percent": round(100 * true_positives / expected, 2) if expected else "",
                "coverage_percent": round(100 * len(predicted) / len(scored), 2) if scored else "",
                "true_positives": true_positives,
                "false_positives": false_positives,
                "false_negatives": false_negatives,
                "evaluated": len(scored),
            })

        pair_predictions = defaultdict(set)
        for link in CaseLink.objects.filter(
            review_state__in=[CaseLink.ReviewState.SUGGESTED, CaseLink.ReviewState.CONFIRMED]
        ):
            pair_predictions[(link.case_a_id, link.case_b_id)].add(link.link_type)
        for expected_type in ("overlap", "conflict"):
            positive = [label for label in link_labels if label.expected_type == expected_type]
            tp = sum(expected_type in pair_predictions.get((label.case_a_id, label.case_b_id), set())
                     for label in positive)
            fp = sum(
                expected_type in pair_predictions.get((label.case_a_id, label.case_b_id), set())
                for label in link_labels if label.expected_type != expected_type
            )
            fn = len(positive) - tp
            rows.append({
                "metric": expected_type,
                "threshold": "",
                "precision_percent": round(100 * tp / (tp + fp), 2) if tp + fp else "",
                "recall_percent": round(100 * tp / len(positive), 2) if positive else "",
                "coverage_percent": "",
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "evaluated": len(link_labels),
            })

        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "benchmark-evaluation.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        svg_path = output_dir / "matching-threshold-sweep.svg"
        self._write_chart(svg_path, rows[:20])

        self.stdout.write(self.style.SUCCESS(
            f"Evaluated {len(scored)} institution labels and {len(link_labels)} link labels."
        ))
        for row in rows:
            self.stdout.write(
                f"{row['metric']} {row['threshold']}: precision={row['precision_percent']}%, "
                f"recall={row['recall_percent']}%, coverage={row['coverage_percent']}%"
            )
        self.stdout.write(f"Saved {csv_path} and {svg_path}")

    @staticmethod
    def _write_chart(path, rows):
        width, height = 900, 500
        left, top, plot_width, plot_height = 76, 44, 760, 350
        palette = {"precision_percent": "#176d62", "recall_percent": "#c06a3a"}
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            '<title id="title">Institution matching threshold sweep</title>',
            '<desc id="desc">Precision and recall measured at thresholds from 0.60 to 0.98 on the labelled synthetic benchmark.</desc>',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            '<text x="76" y="28" font-family="Arial" font-size="20" font-weight="700" fill="#172b3b">Synthetic matching benchmark</text>',
        ]
        for tick in range(0, 101, 20):
            y = top + plot_height * (100 - tick) / 100
            lines.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_width}" y2="{y:.1f}" stroke="#e2e8ec"/>')
            lines.append(f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-family="Arial" font-size="13" fill="#526270">{tick}%</text>')
        for idx, row in enumerate(rows):
            x = left + plot_width * idx / max(1, len(rows) - 1)
            if idx % 2 == 0 or idx == len(rows) - 1:
                lines.append(f'<text x="{x:.1f}" y="{top+plot_height+25}" text-anchor="middle" font-family="Arial" font-size="12" fill="#526270">{html.escape(row["threshold"])}</text>')
        for key, color in palette.items():
            points = []
            for idx, row in enumerate(rows):
                value = row[key]
                if value == "":
                    continue
                x = left + plot_width * idx / max(1, len(rows) - 1)
                y = top + plot_height * (100 - float(value)) / 100
                points.append(f"{x:.1f},{y:.1f}")
            lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{" ".join(points)}"/>')
        lines.extend([
            f'<line x1="{left+220}" y1="{top+plot_height+65}" x2="{left+250}" y2="{top+plot_height+65}" stroke="{palette["precision_percent"]}" stroke-width="3"/>',
            f'<text x="{left+258}" y="{top+plot_height+70}" font-family="Arial" font-size="14" fill="#172b3b">Precision</text>',
            f'<line x1="{left+380}" y1="{top+plot_height+65}" x2="{left+410}" y2="{top+plot_height+65}" stroke="{palette["recall_percent"]}" stroke-width="3"/>',
            f'<text x="{left+418}" y="{top+plot_height+70}" font-family="Arial" font-size="14" fill="#172b3b">Recall</text>',
            '<text x="450" y="480" text-anchor="middle" font-family="Arial" font-size="13" fill="#526270">Threshold · labelled synthetic data only</text>',
            '</svg>',
        ])
        path.write_text("\n".join(lines), encoding="utf-8")
