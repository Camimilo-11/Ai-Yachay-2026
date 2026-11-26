# False-assurance results

| Group | Attempts | N complete | VRR (95% CI) | FAR repairer (95% CI) | FAR reviewer (95% CI) | Caught by reviewer | McNemar p |
|---|---|---|---|---|---|---|---|
| c0 | 30 | 29 | 16/29 = 55.2% (37.5–71.6%) | 12/28 = 42.9% (26.5–60.9%) | 0/0 = undefined (–) | – | – |
| c0g | 30 | 29 | 14/29 = 48.3% (31.4–65.6%) | 14/28 = 50.0% (32.6–67.4%) | 0/0 = undefined (–) | – | – |
| c1 | 30 | 29 | 14/29 = 48.3% (31.4–65.6%) | 13/27 = 48.1% (30.7–66.0%) | 12/26 = 46.2% (28.8–64.5%) | 1 | 1.000 |

## Acceptance rules — c0 (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 29 | 28 | 12 | 42.9% (26.5–60.9%) | 55.2% | – |

## Acceptance rules — c0g (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 29 | 28 | 14 | 50.0% (32.6–67.4%) | 48.3% | – |

## Acceptance rules — c1 (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 29 | 27 | 13 | 48.1% (30.7–66.0%) | 48.3% | – |
| judge1 | 29 | 27 | 13 | 48.1% (30.7–66.0%) | 48.3% | 1.000 |
| consensus | 29 | 26 | 12 | 46.2% (28.8–64.5%) | 48.3% | 1.000 |
| majority | 29 | 27 | 13 | 48.1% (30.7–66.0%) | 48.3% | 1.000 |
| unanimous (primary) | 29 | 26 | 12 | 46.2% (28.8–64.5%) | 48.3% | 1.000 |
| gate | 29 | 19 | 7 | 36.8% (19.1–59.0%) | 41.4% | 0.031 |
| pre_revision | 29 | 25 | 11 | 44.0% (26.7–62.9%) | 48.3% | 0.500 |
| independent | 29 | 21 | 9 | 42.9% (24.5–63.5%) | 41.4% | 0.125 |

## Protocols and debate — c0

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 29 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 300 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 16 (55.2%) |
| ... and the jury selected a correct one | 16 |

## Protocols and debate — c0g

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 29 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 3 (candidates rescued by the feedback: 2) |
| Citations whose quoted code does not exist | 2 of 322 (0.6%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 14 (48.3%) |
| ... and the jury selected a correct one | 14 |

## Protocols and debate — c1

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 10.3% of 29 |
| Resolved: independent vote / after debate / after revision | 21 / 5 / 0 |
| Patch versions rejected by the mechanical gate | 2 (candidates rescued by the feedback: 2) |
| Citations whose quoted code does not exist | 1 of 1535 (0.1%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 14 (48.3%) |
| ... and the jury selected a correct one | 14 |

## In the format of the professor's slides (same definitions)

System claim = the repairer's claim in C0/C0g, the primary acceptance rule where there is a jury.

| Group | Did not apply or broke functionality | Applied, functional, failed security | Positive claims not verified (FAR) | Median generation time per case | Median API time per case | Tokens in / out |
|---|---|---|---|---|---|---|
| c0 | 1/29 | 12/28 | 12/28 = 42.9% | 1021 s | 114 s | 513,789 / 229,725 |
| c0g | 1/29 | 14/28 | 14/28 = 50.0% | 898 s | 98 s | 572,513 / 253,322 |
| c1 | 2/29 | 13/27 | 12/26 = 46.2% | 2722 s | 453 s | 7,019,622 / 1,873,738 |

FAR is 'undefined' when the model made no positive repair claim.
Incomplete attempts are excluded from N and listed in summary.json.
Safe yield = share of attempts that were accepted AND verified.
pre_revision and independent judge the INITIAL patch (V_initial): unanimity before the first revision (secondary, decisiones v1) and unanimity in round 0, before any debate (exploratory, added after the pilot C1 v2 and before the main C1).
