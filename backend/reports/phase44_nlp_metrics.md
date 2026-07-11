# Phase 44 Korean NLP Metrics

- Fixture: 320-case curated Korean NLP regression suite
- Execution: deterministic rule-based path; LLM=false; external optional physics engines used=none
- Environment: GitHub-hosted Ubuntu 24.04, CPython 3.13.14
- Historical pre-audit release gates: **passed**
- Final benchmark failures: none

## Baseline to final

| Metric | Baseline | Final | Delta |
|---|---:|---:|---:|
| case_count | 320 | 320 | 0.000000 |
| status_accuracy | 0.809375 | 1 | 0.190625 |
| subtype_accuracy | not measured | 1 | n/a |
| candidate_coverage_accuracy | not measured | 1 | n/a |
| missing_info_accuracy | not measured | 1 | n/a |
| conflict_symbol_accuracy | not measured | 1 | n/a |
| quantity_precision | 0.980826 | 1 | 0.019174 |
| quantity_recall | 0.915978 | 1 | 0.084022 |
| unit_normalization_accuracy | 0.933884 | 1 | 0.066116 |
| subject_binding_accuracy | 1 | 1 | 0.000000 |
| requested_output_accuracy | 0.634375 | 1 | 0.365625 |
| direction_accuracy | 0.941176 | 1 | 0.058824 |
| assumption_classification_accuracy | 0.835165 | 1 | 0.164835 |
| system_type_top1_accuracy | 0.8875 | 1 | 0.112500 |
| system_type_topk_recall | 0.890625 | 1 | 0.109375 |
| ambiguity_detection_recall | 0.666667 | 1 | 0.333333 |
| unsupported_precision | 0.521739 | 1 | 0.478261 |
| unsupported_recall | 0.6 | 1 | 0.400000 |
| false_solve_rate | 0.252632 | 0 | -0.252632 |
| unnecessary_clarification_rate | 0.12 | 0 | -0.120000 |
| missing_clarification_rate | 0.333333 | 0 | -0.333333 |
| condition_classification_error_rate (legacy name: silent_assumption_rate) | 0.164835 | 0 | -0.164835 |
| silent_assumption_rate | N/A | N/A | per-case allowed-assumption oracle required |
| contradictory_input_detection_rate | 0.75 | 1 | 0.250000 |
| canonical_consistency_accuracy | 0.692308 | 1 | 0.307692 |
| high_confidence_false_solves | 24 | 0 | -24.000000 |

The principal safety result is a false-solve reduction from **25.2632% (24/95)** to **0% (0/95)**. High-confidence false solves fell from **24** to **0**. Ambiguity, unsupported scope, missing information, and contradictory inputs are now measured as distinct states.

## Confidence calibration

| Score bin | Baseline accuracy | Baseline false solves | Final accuracy | Final false solves |
|---|---:|---:|---:|---:|
| 0.00–0.59 | 0 | 0 | N/A (0 samples) | 0 |
| 0.60–0.79 | 0.606742 | 0 | 1.0 | 0 |
| 0.80–1.00 | 0.941463 | 24 | 1.0 | 0 |

## Performance

- Baseline: 4.497 seconds for 320 cases.
- Final: 5.863 seconds for 320 cases (18.322 ms/case).
- Change: +1.366 seconds on a GitHub-hosted runner.

These timings include Python startup and report generation. They establish a reproducible Phase 44 baseline, not a production latency SLO.

## Historical pre-audit validation

| Command | Passed | Failed | Skipped | Deselected | Duration |
|---|---:|---:|---:|---:|---:|
| `python -m pytest backend/tests/test_phase44_korean_nlp_robustness.py -q` | 7 | 0 | 0 | 0 | 5.81 s |
| `python backend/tools/run_phase44_nlp_benchmark.py` | 320 cases | 0 cases | 0 | 0 | 5.863 s |
| `bash scripts/check_backend_fast.sh` | 436 | 0 | 0 | 39 | 28.41 s |
| `python -m pytest backend/tests -q` | 436 | 0 | 0 | 39 | 27.32 s |
| `python -m pytest backend/tests -q -o addopts=` | 475 | 0 | 0 | 0 | 46.22 s |
| `bash scripts/check_frontend_metadata.sh` | 1 check | 0 | 0 | 0 | 0.036 s |

The frontend build was not run because no frontend source or configuration changed. The validation checkout ended with a clean working tree.

## Scope and limitations

The benchmark covers paraphrases, subjects/context, units/symbols, typos/colloquialisms, irrelevant background, multiple objects, ambiguity, missing information, contradictions, and unsupported domains. It does not claim statistical coverage of all Korean student language. Phase 44 does not change solver equations, root selection, routing score policy, or introduce SciPy/PyChrono/Rapier2D architecture.

Machine-readable details, thresholds, environment, failures, and comparison deltas are in `backend/reports/phase44_nlp_metrics.json`.


## Metric safeguards added by the audit

The evaluator now records a numerator, denominator, minimum sample requirement, and sufficiency state for each metric. A required metric with no eligible samples is `N/A / insufficient_samples` and fails its gate. Quantity precision compares every observed quantity with the oracle and explicitly declared compatibility aliases, so an unlisted extra fact is a false positive even when `forbidden_knowns` is absent. System-type top-k is fixed at `k=3`. Empty confidence bins report `N/A`.

The historical `silent_assumption_rate` was the complement of condition classification accuracy and has been renamed `condition_classification_error_rate`. The genuine silent-assumption metric evaluates only solved cases with a per-case `allowed_assumption_kinds` oracle. The 320 historical fixtures do not yet carry that annotation, so the versioned historical value is `N/A`; annotating the complete suite is follow-up work rather than silently treating zero eligible cases as success.

## Benchmark reliability and independence

- Completely identical sentences beyond the first copy: **81**
- Exact unique sentences: **239**
- Numeric-only/template duplicates beyond one representative: **60**
- Unique sentence stimuli after collapsing numeric templates: **179**
- Parser normalization-dictionary surface forms directly present: **8** (`나중 속도`, `도르레`, `마찰 업는`, `매끄런`, `미터퍼세컨드제곱`, `최종 속도`, `최종 속력`, `쵸속도`)

| Category | Cases | Exact unique | Unique stimuli |
|---|---:|---:|---:|
| paraphrase | 80 | 80 | 80 |
| subject_context | 30 | 6 | 6 |
| unit_symbol | 40 | 40 | 39 |
| typo_colloquial | 20 | 10 | 10 |
| irrelevant_background | 25 | 25 | 25 |
| multi_object | 30 | 2 | 2 |
| ambiguity | 30 | 22 | 3 |
| missing_information | 25 | 17 | 5 |
| contradiction | 20 | 20 | 4 |
| unsupported | 20 | 17 | 5 |

The 320 cases are a curated regression suite. They do not prove generalization to the distribution of real student inputs. A 1.0 score applies only to the current fixed fixtures. Benchmark independence is limited by repeated templates and direct parser-dictionary overlap. An external held-out validation set remains follow-up work.
