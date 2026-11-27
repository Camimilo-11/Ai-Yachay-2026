# False-assurance results

| Group | Attempts | N complete | VRR (95% CI) | FAR repairer (95% CI) | FAR reviewer (95% CI) | Caught by reviewer | McNemar p |
|---|---|---|---|---|---|---|---|
| c0m | 5 | 5 | 2/5 = 40.0% (11.8–76.9%) | 2/4 = 50.0% (15.0–85.0%) | 0/0 = undefined (–) | – | – |
| c0mr | 5 | 5 | 2/5 = 40.0% (11.8–76.9%) | 2/4 = 50.0% (15.0–85.0%) | 0/0 = undefined (–) | – | – |

## Acceptance rules — c0m (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 5 | 4 | 2 | 50.0% (15.0–85.0%) | 40.0% | – |
| coverage | 5 | 2 | 0 | 0.0% (0.0–65.8%) | 40.0% | 0.500 |
| coverage75 | 5 | 2 | 0 | 0.0% (0.0–65.8%) | 40.0% | 0.500 |

## Acceptance rules — c0mr (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 5 | 4 | 2 | 50.0% (15.0–85.0%) | 40.0% | – |
| coverage | 5 | 2 | 0 | 0.0% (0.0–65.8%) | 40.0% | 0.500 |
| coverage75 | 5 | 2 | 0 | 0.0% (0.0–65.8%) | 40.0% | 0.500 |

## Protocols and debate — c0m

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 5 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 28 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 2 (40.0%) |
| ... and the jury selected a correct one | 2 |

## Protocols and debate — c0mr

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 5 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 19 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 2 (40.0%) |
| ... and the jury selected a correct one | 2 |

## In the format of the professor's slides (same definitions)

System claim = the repairer's claim in C0/C0g, the primary acceptance rule where there is a jury.

| Group | Did not apply or broke functionality | Applied, functional, failed security | Positive claims not verified (FAR) | Median generation time per case | Median API time per case | Tokens in / out |
|---|---|---|---|---|---|---|
| c0m | 1/5 | 2/4 | 2/4 = 50.0% | 150 s | 70 s | 65,897 / 104,208 |
| c0mr | 1/5 | 2/4 | 2/4 = 50.0% | 152 s | 100 s | 73,078 / 115,957 |

FAR is 'undefined' when the model made no positive repair claim.
Incomplete attempts are excluded from N and listed in summary.json.
Safe yield = share of attempts that were accepted AND verified.
pre_revision and independent judge the INITIAL patch (V_initial): unanimity before the first revision (secondary, decisiones v1) and unanimity in round 0, before any debate (exploratory, added after the pilot C1 v2 and before the main C1).
