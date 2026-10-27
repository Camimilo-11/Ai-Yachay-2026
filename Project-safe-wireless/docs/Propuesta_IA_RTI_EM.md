# Does EM-Based RSS Noise Calibration Improve Radio Tomographic Localization? A Synthetic Study

**Camilo Vásquez**  
School of Mathematical and Computational Sciences, Yachay Tech University, Urcuquí, Ecuador  
**Course:** Artificial Intelligence  
**Instructor:** [Complete before submission]  
**Article type:** Research project proposal

## Abstract

Radio Tomographic Imaging (RTI) reconstructs a spatial attenuation map from changes in received signal strength (RSS) across radio links. The inverse problem is ill posed, so the result depends on both the noise model and the regularization. This study asks whether Expectation-Maximization (EM) can fit a two-component, zero-mean Gaussian mixture to synthetic RSS residuals better than a single Gaussian, and whether that fit improves localization. A Python simulator creates separate reference, calibration, noise-validation, fingerprint, development, and test data. The comparison includes Tikhonov RTI, an EM-derived Fisher-information factor, a mathematically matched Tikhonov control, weighted K-nearest neighbors (K-NN), and a constant room-center prediction. In the preliminary run, the mixture's mean held-out log density was -2.101, compared with -2.145 for the single Gaussian. Across 30 matched-grid test queries, mean localization errors were 3.653 m for Tikhonov RTI, 3.530 m for the Fisher-scaled RTI, 2.529 m for K-NN, and 2.357 m for the center control. The Fisher result matched its equivalent Tikhonov control. This pilot shows that the simulation pipeline runs; it does not show that EM improves localization or that the method works with physical Wi-Fi measurements. The study provides a reproducible comparison that separates noise-model fit from localization performance.

**Keywords:** expectation-maximization; radio tomographic imaging; received signal strength; Gaussian mixture; synthetic data; localization; reproducibility

## 1. Introduction

Device-free radio localization estimates an object's position without asking it to carry a transmitter. In RTI, changes in RSS across radio links are modelled as weighted contributions from cells in a spatial grid. The forward model is \(y = Wx + n\): \(y\) contains the link measurements, \(W\) maps grid cells to links, \(x\) is the unknown attenuation field, and \(n\) is measurement noise. The number of links is often smaller than the number of cells, so the reconstruction is ill posed and needs regularization [1].

EM estimates parameters in probabilistic models with hidden variables [2]. Here, each RSS residual belongs to one of two Gaussian components, but that component label is unknown. A better fit to the residuals would be useful evidence about the noise model; it would not, on its own, show that the estimated position is more accurate. Localization also depends on node geometry, the forward model, regularization, calibration size, and the strength of the target signal.

The experiments examine that distinction with synthetic data. The AI component is statistical parameter estimation: EM learns the mixture parameters, and the RTI pipeline tests whether that calibration helps locate a target. The research question is: **Under which simulated noise conditions does EM improve held-out RSS-noise fit, and does that improvement reduce RTI localization error against matched baselines?**

The study measures EM convergence and held-out noise density separately from localization error. It uses independent data partitions and compares against Tikhonov, K-NN, and a center prediction. The proposal therefore focuses on a reproducible feasibility comparison, with controls that isolate what EM changes in this implementation. It builds on prior work in mixture-based RSS estimation and noise-adaptive RTI rather than introducing a new EM algorithm [1, 4, 5].

## 2. Related Work

Dempster, Laird, and Rubin described EM as a general maximum-likelihood method for models with incomplete data, including finite mixtures [2]. Wu later analysed when EM sequences converge [3]. In practice, reaching the iteration limit or returning a stable parameter vector does not establish that the fitted model suits the data or improves a downstream prediction.

Wilson and Patwari introduced a linear RSS-based RTI model and used Tikhonov regularization to reconstruct attenuation images [1]. They also fitted a two-component Gaussian mixture to measured RSS residuals with EM. The base simulation uses their reported values, \(p=0.548\), \(\sigma_1=0.971\) dB, and \(\sigma_2=3.003\) dB, as fixed generator settings. This project does not measure those parameters. Their experiment used IEEE 802.15.4 sensor nodes, so its measurements are not a Wi-Fi dataset.

Later RTI studies combined mixture models with reconstruction methods. Gao et al. used a Gaussian mixture model and matrix-transform restoration, and evaluated it with simulated and experimental targets [4]. Huang and Yang estimated mixture-noise parameters and the attenuation image together through sparse Bayesian learning (SBL) [5]. In this implementation, the Fisher term is one scalar that changes the Tikhonov regularization. It does not assign different noise weights to individual links, as a link-adaptive estimator would.

Kaltiokallio et al. used EM with Gaussian smoothing to learn RSS model parameters for device-free localization and tracking, then evaluated the method on measured data from two environments [6]. Their experiments track moving targets; this project uses static synthetic queries on one grid. RADAR provides an earlier example of RF localization from signal strengths and known locations [7]. The K-NN method here is a weighted fingerprint baseline with synthetic data, rather than a reproduction of RADAR.

| Reference | Main idea and method | Data and evaluation | Relevance and limitation for this study |
|---|---|---|---|
| Wilson & Patwari [1] | Linear RTI, ellipse weights, Tikhonov reconstruction; EM fit of a two-Gaussian RSS-noise mixture. | Measurements from a deployed sensor network; noise characterization, image-error bounds, and localization images. | Establishes the RTI and mixture-noise foundation and supplies the base mixture values. Its radio system and empirical deployment are not recreated here. |
| Gao et al. [4] | Gaussian-mixture-based RTI image restoration using a matrix transform and constrained least-squares filter. | Simulated and experimental target evaluation. | Shows that mixture models have been combined with image reconstruction. The restoration algorithm differs from the scalar Fisher/Tikhonov extension in this repository. |
| Huang & Yang [5] | MoG noise and attenuation image estimated jointly with sparse Bayesian learning and EM updates. | Indoor RTI experiments, including a 20-node, 6 m × 4 m setup with predefined target positions; compares localization behavior under complex noise. | Provides a stronger noise-adaptive method and a benchmark for future extensions. It is not implemented in the current code. |
| Kaltiokallio et al. [6] | EM with Gaussian smoothing estimates RSS model parameters for device-free localization and tracking. | 18 measured datasets from two environments; reports tracking/localization evaluation against a benchmark system. | Demonstrates EM-based calibration with real RSS. It uses dynamic tracking and measured channels, unlike this static synthetic study. |
| Bahl & Padmanabhan [7] | RADAR combines received signal strengths and an empirical location database for in-building localization. | Empirical measurements in a building; reports location error. | Motivates a fingerprint comparison. The present weighted K-NN uses synthetic fingerprints and does not reproduce RADAR. |

## 3. Materials and Methods

### 3.1. Study design and data generation

This is an applied computational study using simulated measurements. The generator places radio nodes around a rectangular area, builds the ellipse-based weight matrix \(W\), draws one target attenuation field \(x\), and generates link changes using \(y=Wx+n\). It records RSS as the reference level minus the generated attenuation. Each CSV row identifies its link and data phase; missing measurements are marked explicitly, and the target position is saved separately as ground truth.

The base mixture uses Wilson and Patwari's published values [1]. The quick run has six nodes, 15 links, 36 grid cells, and 30 test queries. The larger base run uses 12 nodes, 66 links, 100 cells, and 120 test queries. Both configurations save separate reference, calibration, validation, fingerprint, development, and test data. The simulator can vary noise spread, quantization, temporal correlation, link loss, baseline drift, carrier frequency, and receiver margin. In this model, carrier frequency changes the illustrative free-space link budget and which weak links are censored; it does not change the spatial weight matrix or simulate signal penetration through materials.

**System diagram.** The course requires this figure to be drawn by the student. Add the finished diagram here; the components to include are listed in `docs/DIAGRAMA_PENDIENTE_DE_DISENO_MANUAL.md`.

### 3.2. Inputs, partitions, and algorithms

The estimator receives calibration residuals after the reference estimate has been subtracted. The C++17 EM code estimates the mixture weight \(p\) and both standard deviations while holding the component means at zero. A separate validation block compares the fitted mixture's average held-out log density with that of a single Gaussian. This measures how well each distribution predicts residuals; it does not measure localization accuracy.

The generator uses separate random streams for reference, calibration, noise validation, fingerprints, development, and test data. Development data selects regularization \(\alpha\) and K; test data is reserved for scoring. K-NN fingerprints cover the same grid as the test locations but have independent noise draws. The current experiment therefore tests localization within a known grid. It does not test unseen positions, moving trajectories, multiple targets, or transfer to a different environment.

The localization comparison includes five methods: (1) Tikhonov RTI, (2) RTI with a Fisher factor calculated from the EM mixture, (3) a Tikhonov control with the equivalent regularization, (4) inverse-distance weighted K-NN on synthetic fingerprints, and (5) a constant prediction at the room center. In this implementation, the Fisher factor only rescales the Tikhonov penalty. The matched control checks that algebra; the equality does not demonstrate link-specific noise handling.

### 3.3. Metrics and planned experiments

For noise fit, the study records EM convergence, estimated parameters, and mean held-out log density (natural log per residual; residuals are in dB). For localization, it reports mean Euclidean error, RMSE in meters, and coverage. The saved tables identify missing predictions and any center fallback. The current pilot uses one seed. The final evaluation will repeat the base and stress scenarios with independent seeds, summarize variation across runs, and compare methods on the same test queries.

The next stage will first reproduce the nine-scenario pilot, then repeat it across seeds to measure variability and convergence. The larger base geometry will also be run with several seeds. Correlated-noise and low-margin cases will be reported as failures or insufficient calibration whenever the estimator cannot fit the data. Each run saves its configuration, code hashes, generated CSVs, predictions, and summary. The main pipeline uses Python, NumPy, Matplotlib, and the existing C++17 EM code. Optional pandas and SciPy are only needed for diagnostics adapted from the upstream repository.

### 3.4. Baselines and validity checks

Tikhonov RTI is the main algorithmic baseline, following the foundational RTI formulation [1]. Its equivalent-regularization control checks whether the Fisher factor does anything beyond changing the penalty strength. Weighted K-NN provides a fingerprint comparison inspired by RF location systems [7], and the room-center prediction checks whether the signal-based methods improve on a simple spatial prior. Calibration and validation data are disjoint. Hyperparameters are selected with development data and are fixed before test scoring.

The simulator also checks that CSV values survive a write-read cycle, link identities remain consistent, missing values stay marked, and each run records its parameter sources. Correlated noise violates the independence assumption of the base mixture model, and EM may fail to converge under that condition. When a low receiver margin leaves too few calibration residuals, the run stops before fitting. In either case, the summary reports the failure or insufficient calibration and omits a localization score when the pipeline cannot validly produce one.

## 4. Preliminary Results

The quick base run used seed 7, six nodes, 15 links, 36 cells, and 30 test queries. EM converged after 294 iterations using 900 calibration residuals. It estimated \(\hat p=0.541\), \(\hat\sigma_1=1.060\) dB, and \(\hat\sigma_2=2.938\) dB. For 450 held-out residuals, the mixture's mean log density was -2.101; the single Gaussian's was -2.145. The difference is small and comes from one generated split.

| Method | Mean localization error (m) | RMSE (m) | Coverage |
|---|---:|---:|---:|
| Tikhonov RTI | 3.653 | 4.113 | 30/30 |
| EM-derived Fisher RTI | 3.530 | 4.015 | 30/30 |
| Matched Tikhonov | 3.530 | 4.015 | 30/30 |
| Weighted K-NN | 2.529 | 2.836 | 30/30 |
| Constant room center | 2.357 | 2.517 | 30/30 |

The center prediction has the lowest mean error in this pilot, while K-NN performs better than either RTI setting. The Fisher-based RTI and its equivalent Tikhonov control agree to numerical precision, as expected from the equations. In the stress suite, EM did not converge within 600 iterations when temporal correlation was set to \(\rho=0.8\). At 5 GHz with a low receiver margin, only 1.3% of test measurements remained valid, so the run was marked insufficient for calibration. These outcomes come from simulated conditions, not a measured radio channel.

The files under `results/integracion_verificada/` contain the reported values. The table uses `base_r00/summary.json` and can be regenerated with the command in the README. This is an executed simulation with one seed; it is not a physical experiment.

## 5. Discussion and Expected Research Direction

The pilot shows that the mixture can be fitted and the RTI and fingerprint methods can run from generated CSV files. It also separates two different outcomes: the mixture has a slightly better held-out residual score, but none of the signal-based methods beats the room-center prediction in mean location error. The Fisher-based RTI offers no change beyond its effective regularization; the matched Tikhonov control produces the same result.

The next stage should repeat each scenario with several seeds and report variation in both residual scores and location errors. It should also measure parameter recovery, since the simulator's true mixture parameters are known, and check predictive fit under quantization, drift, missing links, and correlation. A future extension could estimate link-specific responsibilities together with the attenuation field, following the broader direction of noise-adaptive RTI [5]. That would require a separate implementation and evaluation.

The pilot has several limits. Its base case uses synthetic independent noise; fingerprint and test locations share one grid; and each query contains one stationary target. The propagation model uses geometry rather than electromagnetic simulation, so reflections, diffraction, wall absorption, IEEE 802.11 MAC behavior, and CSI are outside its scope. Results from measured RSS and CSI studies provide context but do not predict this simulator's performance [1, 5, 6].

This study provides a reproducible comparison of mixture fitting and localization, with controls for regularization strength and a no-signal position prior. The pilot provides no evidence that EM improves position estimates. Conclusions will depend on repeated runs and apply only to the simulated conditions.

## Data Availability Statement

The generator, configuration, preliminary synthetic CSV files, predictions, summaries, and plotting outputs are included in this project directory. No external dataset is required to reproduce the reported preliminary simulation. The intended GitHub location is listed in the README; it should be checked for accessibility after the local repository changes are synchronized.

## 6. References

1. Wilson, J.; Patwari, N. Radio Tomographic Imaging with Wireless Networks. *IEEE Transactions on Mobile Computing* **2010**, *9*(5), 621–632. https://doi.org/10.1109/TMC.2009.174.
2. Dempster, A.P.; Laird, N.M.; Rubin, D.B. Maximum Likelihood from Incomplete Data via the EM Algorithm. *Journal of the Royal Statistical Society: Series B (Methodological)* **1977**, *39*(1), 1–22. https://doi.org/10.1111/j.2517-6161.1977.tb01600.x.
3. Wu, C.F.J. On the Convergence Properties of the EM Algorithm. *The Annals of Statistics* **1983**, *11*(1), 95–103. https://doi.org/10.1214/aos/1176346060.
4. Gao, F.; Sun, C.; Liu, H.; An, J.; Xu, S. An Image Restoration Method Using Matrix Transform and Gaussian Mixture Model for Radio Tomographic Imaging. *Wireless Communications and Mobile Computing* **2017**, Article 5703518. https://doi.org/10.1155/2017/5703518.
5. Huang, K.; Yang, Z. Noise Adaptive Optimization Scheme for Robust Radio Tomographic Imaging Based on Sparse Bayesian Learning. *IEEE Access* **2020**, *8*, 118174–118182. https://doi.org/10.1109/ACCESS.2020.3005048.
6. Kaltiokallio, O.; Hostettler, R.; Yiğitler, H.; Valkama, M. Unsupervised Learning in RSS-Based DFLT Using an EM Algorithm. *Sensors* **2021**, *21*(16), 5549. https://doi.org/10.3390/s21165549.
7. Bahl, P.; Padmanabhan, V.N. RADAR: An In-Building RF-Based User Location and Tracking System. In *Proceedings of IEEE INFOCOM 2000*; Vol. 2, pp. 775–784. https://doi.org/10.1109/INFCOM.2000.832252.
