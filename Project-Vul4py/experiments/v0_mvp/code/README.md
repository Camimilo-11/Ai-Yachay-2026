# Implementation snapshot

This folder contains selected files from the Vul4Py checkout used for the five-case experiment. It is a reviewable snapshot, not a complete standalone checkout.

- scripts/run_agent.py saves the model's claim, confidence, raw response, patch, and generation metadata.
- scripts/run_eval.py applies each saved patch and runs functional and exploit tests.
- scripts/vul4py.py provides the evaluation support code.
- dataset/vul4py_5.csv is the five-case dataset subset.
- vul4py_gitignore.txt contains the ignore rules used for local workspaces and generated files.

The final results use the instructor-approved NVIDIA endpoint and model poolside/laguna-xs-2.1. The runner's gpt label is internal; it does not identify the API provider. The evaluation used one saved response per vulnerability. Some API calls failed before those responses were saved, and the final CSV has no generation timestamp. See the parent README for results and limitations.

A full rerun needs the original Vul4Py repository, prepared workspaces, Python dependencies, and an API key supplied through an environment variable. This snapshot includes no key, virtual environment, or full benchmark workspace.