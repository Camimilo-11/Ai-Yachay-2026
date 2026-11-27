# False-assurance results

| Group | Attempts | N complete | VRR (95% CI) | FAR repairer (95% CI) | FAR reviewer (95% CI) | Caught by reviewer | McNemar p |
|---|---|---|---|---|---|---|---|
| c1 | 5 | 5 | 3/5 = 60.0% (23.1–88.2%) | 2/5 = 40.0% (11.8–76.9%) | 1/4 = 25.0% (4.6–69.9%) | 1 | 1.000 |
| c1v2 | 5 | 5 | 3/5 = 60.0% (23.1–88.2%) | 2/5 = 40.0% (11.8–76.9%) | 2/5 = 40.0% (11.8–76.9%) | 0 | – |
| rep_gpt-5.4-mini | 5 | 5 | 1/5 = 20.0% (3.6–62.4%) | 4/5 = 80.0% (37.6–96.4%) | 0/0 = undefined (–) | – | – |
| rep_gpt-6.2-sol | 5 | 5 | 3/5 = 60.0% (23.1–88.2%) | 2/5 = 40.0% (11.8–76.9%) | 0/0 = undefined (–) | – | – |

## Acceptance rules — c1 (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 5 | 5 | 2 | 40.0% (11.8–76.9%) | 60.0% | – |
| judge1 | 5 | 4 | 1 | 25.0% (4.6–69.9%) | 60.0% | 1.000 |
| consensus | 5 | 4 | 1 | 25.0% (4.6–69.9%) | 60.0% | 1.000 |
| majority | 5 | 4 | 1 | 25.0% (4.6–69.9%) | 60.0% | 1.000 |
| unanimous (primary) | 5 | 4 | 1 | 25.0% (4.6–69.9%) | 60.0% | 1.000 |
| gate | 5 | 4 | 1 | 25.0% (4.6–69.9%) | 60.0% | 1.000 |

## Acceptance rules — c1v2 (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 5 | 5 | 2 | 40.0% (11.8–76.9%) | 60.0% | – |
| judge1 | 5 | 5 | 2 | 40.0% (11.8–76.9%) | 60.0% | – |
| consensus | 5 | 5 | 2 | 40.0% (11.8–76.9%) | 60.0% | – |
| majority | 5 | 5 | 2 | 40.0% (11.8–76.9%) | 60.0% | – |
| unanimous (primary) | 5 | 5 | 2 | 40.0% (11.8–76.9%) | 60.0% | – |
| gate | 5 | 3 | 0 | 0.0% (0.0–56.1%) | 60.0% | 0.500 |

## Acceptance rules — rep_gpt-5.4-mini (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 5 | 5 | 4 | 80.0% (37.6–96.4%) | 20.0% | – |

## Acceptance rules — rep_gpt-6.2-sol (tau = 0.8, primary = unanimous)

| Rule | N | Accepted | False assurance | FAR (95% CI) | Safe yield | McNemar p vs repairer |
|---|---|---|---|---|---|---|
| repairer | 5 | 5 | 2 | 40.0% (11.8–76.9%) | 60.0% | – |

## Protocols and debate — c1

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 20.0% of 5 |
| Resolved: independent vote / after debate / after revision | 2 / 2 / 0 |
| Patch versions rejected by the mechanical gate | 5 (candidates rescued by the feedback: 2) |
| Citations whose quoted code does not exist | 0 of 415 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 3 (60.0%) |
| ... and the jury selected a correct one | 3 |

## Protocols and debate — c1v2

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 5 |
| Resolved: independent vote / after debate / after revision | 2 / 2 / 1 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 256 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 3 (60.0%) |
| ... and the jury selected a correct one | 3 |

## Protocols and debate — rep_gpt-5.4-mini

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 5 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 16 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 1 (20.0%) |
| ... and the jury selected a correct one | 1 |

## Protocols and debate — rep_gpt-6.2-sol

| Measure | Value |
|---|---|
| Abstained (no unanimous verdict) | 0.0% of 5 |
| Resolved: independent vote / after debate / after revision | 0 / 0 / 0 |
| Patch versions rejected by the mechanical gate | 0 (candidates rescued by the feedback: 0) |
| Citations whose quoted code does not exist | 0 of 36 (0.0%) |
| Refusals | 0 |
| Cases where some candidate was correct (oracle-best VRR) | 3 (60.0%) |
| ... and the jury selected a correct one | 3 |

## In the format of the professor's slides (same definitions)

System claim = the repairer's claim in C0/C0g, the primary acceptance rule where there is a jury.

| Group | Did not apply or broke functionality | Applied, functional, failed security | Positive claims not verified (FAR) | Median generation time per case | Median API time per case | Tokens in / out |
|---|---|---|---|---|---|---|
| c1 | 0/5 | 2/5 | 1/4 = 25.0% | 692 s | 629 s | 718,437 / 502,775 |
| c1v2 | 0/5 | 2/5 | 2/5 = 40.0% | 530 s | 503 s | 492,189 / 329,137 |
| rep_gpt-5.4-mini | 2/5 | 2/3 | 4/5 = 80.0% | 268 s | 104 s | 36,552 / 129,292 |
| rep_gpt-6.2-sol | 0/5 | 2/5 | 2/5 = 40.0% | 100 s | 55 s | 36,552 / 25,080 |

FAR is 'undefined' when the model made no positive repair claim.
Incomplete attempts are excluded from N and listed in summary.json.
Safe yield = share of attempts that were accepted AND verified.
