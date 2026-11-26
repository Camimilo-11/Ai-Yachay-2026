# v1: a working oracle for the 100 Vul4Py cases

Up to November 24, 2026. With the public Vul4Py release (commit `f80f861`) only 18 of the 100 cases passed the
first scan in a sandbox the size of the instance: missing test dependencies, Python 3.11 with 2026 libraries
for fixes from 2017-2025, tests that fail even with the upstream fix, suites that hang, and a harness that
deletes the products of the install. The repairs change how a case is installed or which tests run, never a
test or what it expects, and each one is recorded with its reason in `dataset/meta_overrides/<case>.json`
(`_note`). The repair levels are described in `docs/README_multiagent.md`.

Result: every case passed the scan on the instance after the build rounds (R0: 86, R1: 98, R2-R4: 99,
R5: 100) and all 100 passed the oracle control (the functional tests pass unpatched, the exploit tests fail
unpatched, and the upstream fix passes both). See `figures/fig_environment.pdf`.

| File | Content |
|---|---|
| `scan_report_round0.tsv` ... `round5.tsv`, `scan_report.tsv` | scan of every case per build round (status OK, UNEXPECTED, INFRA_BROKEN) |
| `oracle_report.tsv` | oracle control of every case (unpatched and upstream-fix test counts) |
| `oracle_validation_mvp_cases.csv` | the first oracle validation, on the five v0 cases |
| `environment.txt`, `pip_constraints.txt` | instance environment and pip constraints |
| `../dataset/` | the 91 meta_overrides and 14 test_overrides |
| `../logs/console/v1_build.log` | console of the build |
| `../prereg/decisiones_v1.txt` | decisions fixed before the first pipeline run |
