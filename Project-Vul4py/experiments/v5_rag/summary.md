# False-assurance results

| Group | Attempts | N complete | VRR (95% CI) | FAR repairer (95% CI) | FAR reviewer (95% CI) | Caught by reviewer | McNemar p |
|---|---|---|---|---|---|---|---|
| c0 | 95 | 94 | 38/94 = 40.4% (31.1–50.5%) | 54/91 = 59.3% (49.1–68.9%) | 0/0 = undefined (–) | – | – |
| c0m | 95 | 95 | 14/95 = 14.7% (9.0–23.2%) | 48/62 = 77.4% (65.6–86.0%) | 0/0 = undefined (–) | – | – |
| c0mr | 95 | 94 | 13/94 = 13.8% (8.3–22.2%) | 45/58 = 77.6% (65.3–86.4%) | 0/0 = undefined (–) | – | – |

## Acceptance rules — c0 (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 94 | 91 | 54 | 59.3% (49.1–68.9%) | 39.4% | – |
| coverage | 94 | 36 | 14 | 38.9% (24.8–55.1%) | 23.4% | 0.000 |
| coverage75 | 94 | 44 | 18 | 40.9% (27.7–55.6%) | 27.7% | 0.000 |

## Acceptance rules — c0m (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 95 | 62 | 48 | 77.4% (65.6–86.0%) | 14.7% | – |
| coverage | 95 | 19 | 10 | 52.6% (31.7–72.7%) | 9.5% | 0.000 |
| coverage75 | 95 | 19 | 10 | 52.6% (31.7–72.7%) | 9.5% | 0.000 |

## Acceptance rules — c0mr (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 94 | 58 | 45 | 77.6% (65.3–86.4%) | 13.8% | – |
| coverage | 94 | 15 | 8 | 53.3% (30.1–75.2%) | 7.4% | 0.000 |
| coverage75 | 94 | 16 | 8 | 50.0% (28.0–72.0%) | 8.5% | 0.000 |

## Protocols and debate — c0

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 94 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 940 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 38 (40.4%) |
| ... and the jury selected a correct one | 38 |

## Protocols and debate — c0m

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 95 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 1 of 521 (0.2%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 14 (14.7%) |
| ... and the jury selected a correct one | 14 |

## Protocols and debate — c0mr

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 94 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 548 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 13 (13.8%) |
| ... and the jury selected a correct one | 13 |

## In the format of the professor's slides (same definitions)

System claim = the repairer's claim in C0/C0g, the primary acceptance rule where there is a jury.

| Group | Did not apply or broke functionality | Applied, functional, failed security | Positive claims not verified (FAR) | Median generation time per case | Median API time per case | Tokens in / out |
|---|---|---|---|---|---|---|
| c0 | 8/94 | 48/86 | 54/91 = 59.3% | 1332 s | 98 s | 1,362,127 / 671,977 |
| c0m | 39/95 | 42/56 | 48/62 = 77.4% | 2167 s | 82 s | 2,226,545 / 2,400,652 |
| c0mr | 40/94 | 41/54 | 45/58 = 77.6% | 1762 s | 71 s | 2,378,287 / 1,984,738 |

FAR is 'undefined' when the model made no positive repair claim.
Incomplete attempts are excluded from N and listed in summary.json.
Safe yield = share of attempts that were accepted AND verified.
pre_revision and independent judge the INITIAL patch (V_initial): unanimity before the first revision (secondary, decisiones v1) and unanimity in round 0, before any debate (exploratory, added after the pilot C1 v2 and before the main C1).
