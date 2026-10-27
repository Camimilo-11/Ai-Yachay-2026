# Results summary (generated from CSVs)

All observations are synthetic. The localization comparison uses the same 500 query cases for each method.
Positive paired error reduction means the candidate had lower error than its baseline.

## EM parameter recovery

| n | Convergence rate | MAE p1 | MAE sigma1 (dB) | MAE sigma2 (dB) | Mean iterations |
|---:|---:|---:|---:|---:|---:|
| 100 | 95% | 0.1048 | 0.1671 | 0.4036 | 182.2 |
| 500 | 100% | 0.0375 | 0.0509 | 0.1230 | 147.6 |
| 1000 | 100% | 0.0381 | 0.0501 | 0.1140 | 159.5 |
| 5000 | 100% | 0.0158 | 0.0194 | 0.0479 | 144.6 |
| 10000 | 100% | 0.0109 | 0.0149 | 0.0325 | 141.9 |

## Initialization sensitivity

20/20 starting values met the stopping criterion on the same sample. Iterations ranged from 85 to 150.
Final p1 estimates ranged from 0.534697 to 0.534698. This is a repeatability check on one sample, not a guarantee of global convergence.

## Localization

| Method | Mean error (m) | 95% bootstrap CI (m) | RMSE (m) |
|---|---:|---:|---:|
| Tikhonov RTI | 3.244 | [3.064, 3.423] | 3.840 |
| EM-Fisher extension | 3.062 | [2.872, 3.246] | 3.698 |
| K-NN fingerprint baseline | 2.618 | [2.510, 2.722] | 2.891 |
| Constant center control | 2.407 | [2.334, 2.481] | 2.562 |

## Paired differences

| Baseline | Candidate | Mean error reduction (m) | Paired 95% CI (m) |
|---|---|---:|---:|
| Tikhonov RTI | EM-Fisher extension | 0.182 | [0.067, 0.299] |
| Tikhonov RTI | K-NN fingerprint baseline | 0.626 | [0.420, 0.832] |
| EM-Fisher extension | K-NN fingerprint baseline | 0.444 | [0.236, 0.650] |
| Constant center control | Tikhonov RTI | -0.837 | [-1.032, -0.637] |
| Constant center control | EM-Fisher extension | -0.655 | [-0.855, -0.457] |
| Constant center control | K-NN fingerprint baseline | -0.212 | [-0.301, -0.121] |

## Localization utility against a control

The lowest mean error in these 500 cases is obtained by Constant center control (2.407 m).
The constant-center control uses no RSSI observations. Pairwise differences above show whether an observation-based method improves on that control; negative reductions mean it performs worse.
The Fisher extension changes the effective regularization from alpha to alpha/gamma. Its difference from fixed-alpha Tikhonov does not isolate a gain attributable to EM; alpha requires independent tuning before such a claim.

## Scope note

The experiment generates RSSI-like observations from an ellipsoidal linear RTI model and a two-component zero-mean Gaussian noise mixture. It does not simulate electromagnetic propagation, walls, rubble, or real Wi-Fi hardware.
