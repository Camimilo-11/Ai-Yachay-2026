# Console notes

## October 12: setup checks

The screenshots in evidence.docx show an isolated CVE-2017-16615 test checkout. Test collection first failed because the environment could not import past. Installing future 1.0.0 allowed the YAML security test to pass. A separate run finished with 16 passed and one SQLAlchemy deprecation warning.

These screenshots document setup only; they are not the final five-case evaluation.

## October 13–14: NVIDIA run

With the instructor's approval, I used NVIDIA's API-compatible endpoint and model poolside/laguna-xs-2.1. The final generation and evaluation files are dated October 14, 2026. Some requests failed with HTTP 410, 403, or 503; I resubmitted after some errors. The final results contain one saved response per case, but not a complete record of every API request. The CSV also lacks the exact generation timestamp.

My classmates used GPT without similar connection problems. This is informal context, not a provider comparison.

The final evaluation verified one repair out of five (VRR 20%). Three of four positive claims were not verified (FAR 75%). See results.csv for case-level counts. The earlier 16-test run is separate from these results.