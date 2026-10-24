# Synthetic benchmark results

Generated locally on 24 October 2026 after seeding 800 institutions and 4,144 demo cases. The matching benchmark contains 24 labels: 12 expected matches and 12 expected non-matches. Link evaluation contains 450 labelled pairs: 120 planted overlaps, 30 planted conflicts and 300 sampled no-link pairs.

| Evaluation | Precision | Recall | Coverage | Sample |
|---|---:|---:|---:|---:|
| Institution matching at threshold 0.90 | 100% | 100% | 50% | 24 cases, 12 positive |
| Overlap suggestions | 80% | 100% | — | 450 case pairs |
| Conflict suggestions | 100% | 100% | — | 450 case pairs |

The threshold sweep measured 100% precision, 100% recall and 50% coverage from 0.60 through 0.92. At 0.94 and above it returned no positive predictions. Overlap precision counts the 30 conflict-labelled cases as false-positive overlap predictions because the synthetic label schema assigns one expected type per pair.

These small generated samples are useful for checking command output and matching workflow. They are not independent real-world cases, do not establish production accuracy, and do not validate the plan's target thresholds. Replace them with a mentor-approved ground-truth set before making operational claims.

Recreate the report after migrations and seed commands:

```powershell
python manage.py seed_demo
python manage.py seed_match_benchmark
python manage.py evaluate_benchmarks
```

The CSV and threshold chart are written to `artifacts/evaluation/`.
