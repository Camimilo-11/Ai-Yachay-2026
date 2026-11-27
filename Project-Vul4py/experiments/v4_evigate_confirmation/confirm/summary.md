# False-assurance results

| Group | Attempts | N complete | VRR (95% CI) | FAR repairer (95% CI) | FAR reviewer (95% CI) | Caught by reviewer | McNemar p |
|---|---|---|---|---|---|---|---|
| c0 | 65 | 63 | 22/63 = 34.9% (24.3–47.2%) | 40/61 = 65.6% (53.0–76.3%) | 0/0 = undefined (–) | – | – |

## Acceptance rules — c0 (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 63 | 61 | 40 | 65.6% (53.0–76.3%) | 33.3% | – |
| coverage | 63 | 23 | 11 | 47.8% (29.2–67.0%) | 19.0% | 0.000 |
| coverage75 | 63 | 27 | 13 | 48.1% (30.7–66.0%) | 22.2% | 0.000 |

## Protocols and debate — c0

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 63 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 620 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 22 (34.9%) |
| ... and the jury selected a correct one | 22 |

## In the format of the professor's slides (same definitions)

System claim = the repairer's claim in C0/C0g, the primary acceptance rule where there is a jury.

| Group | Did not apply or broke functionality | Applied, functional, failed security | Positive claims not verified (FAR) | Median generation time per case | Median API time per case | Tokens in / out |
|---|---|---|---|---|---|---|
| c0 | 7/63 | 34/56 | 40/61 = 65.6% | 1589 s | 86 s | 848,338 / 442,252 |

FAR is 'undefined' when the model made no positive repair claim.
Incomplete attempts are excluded from N and listed in summary.json.
Safe yield = share of attempts that were accepted AND verified.
pre_revision and independent judge the INITIAL patch (V_initial): unanimity before the first revision (secondary, decisiones v1) and unanimity in round 0, before any debate (exploratory, added after the pilot C1 v2 and before the main C1).
