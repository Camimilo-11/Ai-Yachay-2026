# Code

Everything here runs inside a checkout of Vul4Py at commit `f80f861`: copy `scripts/*` into its `scripts/` folder,
`dataset/*` into its `dataset/` folder and `models.json` into its root. The pipeline, the environment repairs and the
commands are described in [`docs/README_multiagent.md`](docs/README_multiagent.md).

| Folder or file | Content |
|---|---|
| `scripts/` | Our scripts (pipeline, evaluator, metrics, confirmatory analyses, retrieval, evigate adapter) and the Vul4Py scripts we changed; Vul4Py's MIT license is in `scripts/LICENSE-Vul4Py` |
| `dataset/` | Environment repairs: 91 `meta_overrides` and 14 `test_overrides`, each with its reason in `_note` |
| `tools/calls_table.py` | Builds `results/logs/calls/*.csv` from the frozen run records, with list prices |
| `docs/` | README of the multi-model pipeline: environment levels, pipeline, configuration, how to run |
| `models.json` | Models, context sizes, reasoning effort and list prices (USD per million tokens) |
| `requirements.txt` | Python packages of the project's virtual environment |

Some scripts are fixed by hash in the decisions files (`../prereg/`), so they are kept exactly as they ran.
