## Review

### P1

**The infinite-loop claim is wrong.** Another reviewer said an empty unsupported file makes `_has_pickle_globals` spin forever. It does not. `pickletools.genops` always reads at least one byte. When it reads an empty byte at EOF, it raises `ValueError` ("pickle exhausted before seeing STOP"). P1 catches `except (ValueError, OverflowError): return False`, so the outer `while True` ends. I reject that counterexample.

**Wildcard-submodule change works as far as it goes.** The original code looks up the module by exact name:

- `unsafe_filter = _unsafe_globals.get(g.module)` (scanner.py:312)
- `unsafe_filter == "*" or g.name in unsafe_filter` (scanner.py:320)

So `asyncio.unix_events` or `asyncio.subprocess` falls through to `Suspicious` (scanner.py:330). P1's prefix check with `module + "."` correctly escalates these to `"*"`. Named rules are left unchanged.

**The renamed-file bypass is fixed only for local directories.** I concede the other reviewers' point that the same filter still exists elsewhere:

- `scan_zip_bytes` still selects members by extension or magic bytes (`if file_ext in _pickle_file_extensions or any(`, line 399). A protocol-0 pickle `payload.txt` inside a `.zip` (`cos\nsystem\n(S'echo pwned'\ntR.`) is still skipped.
- `scan_huggingface_model` still filters by extension (line 509 onward).

The hint lists 494-501 and 507-511 (the Hugging Face scanner) and 392-401 (zip member selection) as upstream change locations. P1 touches neither, which strongly suggests the upstream fix covers paths P1 leaves open.

**Functionality regression.** P1 now opens every regular file in a scanned directory and parses it with `genops`. Any file whose first byte is `c` (GLOBAL) or `i` (INST) followed by two lines counts as "having globals". The common case is a Python file beginning `import os\nimport sys\nfrom ...`:

1. `i` is parsed as INST, with arguments `mport os` / `import sys`.
2. `_has_pickle_globals` returns True and the file goes to `scan_bytes`, then `scan_pickle_bytes`.
3. In `_list_globals`, the INST global is added via `globals.add(tuple(op_value.split(" ", 1)))` (line 252).
4. The next byte `f` is not an opcode, so `genops` fails and `GenOpsError` is raised with those globals.
5. The result has `scan_err=True`, and the CLI then hits `if scan_result.scan_err:` (cli.py:83) and returns 2.

So scanning a model directory that contains a `modeling_*.py` file changes the exit code from 0 to 2. Config files starting with `c` behave the same way. This breaks existing behaviour.

**Conclusion.** P1 is a partial hardening. It leaves the zip and Hugging Face bypasses that the hint points at, and it introduces scan-error regressions in ordinary directory scans.

## Verdict

```json
{"candidates": {"P1": {"removes_vulnerability": 0, "preserves_functionality": 0, "claim": 0, "confidence": 0.05, "evidence": [{"file": "src/picklescan/scanner.py", "line": 312, "quote": "unsafe_filter = _unsafe_globals.get(g.module)"}, {"file": "src/picklescan/scanner.py", "line": 399, "quote": "if file_ext in _pickle_file_extensions or any("}, {"file": "src/picklescan/scanner.py", "line": 252, "quote": "globals.add(tuple(op_value.split(\" \", 1)))"}, {"file": "src/picklescan/cli.py", "line": 83, "quote": "if scan_result.scan_err:"}], "counterexample": "A zip member payload.txt containing protocol-0 pickle 'cos\\nsystem\\n(S\\'echo pwned\\'\\ntR.' is still skipped by scan_zip_bytes, and a Hugging Face file with an unlisted extension is still skipped. Separately, a directory containing a .py file starting 'import os\\nimport sys\\nfrom x import y' is now parsed as a pickle (INST opcode), yields scan_err=True, and makes the CLI return 2 instead of 0."}}, "best": "none"}
```
