## Review

**P1** fixes two things that I could not tie to the upstream change locations, and it changes behaviour in ways that risk regressions.

- **Submodule wildcard.** P1 extends `"*"` rules in `_unsafe_globals` to dotted submodules (`g.module.startswith(module + ".")`). This hardens the denylist. The lookup is still an exact-name match: `unsafe_filter = _unsafe_globals.get(g.module)` (scanner.py:312). Non-wildcard entries are unchanged, for example `"functools": "partial"` and `"operator": "attrgetter"`.
- **Fixed-scope concern.** The hint points to many scattered edits in the scanner and CLI. These include the `_list_globals` area, `scan_pickle_bytes`, `_build_scan_result_from_raw_globals`, the zip, numpy and torch paths, `scan_huggingface_model`, and the exit-code logic in the CLI. This suggests a broader problem, such as error handling, scan-error propagation, or input handling. P1 touches none of these. I cannot see the upstream fix, so this is an inference rather than a confirmed gap.
- **Failure-path bypass remains.** `scan_zip_bytes` only catches `(zipfile.BadZipFile, RuntimeError)` and merely logs a warning (scanner.py:~303). A broken member or a non-string `STACK_GLOBAL` parse error can therefore be hidden from the result, and P1 leaves this behaviour as it is. The `ValueError` raised when `STACK_GLOBAL` has fewer than two values (scanner.py:~280) also propagates unchanged. `main()` handles it by logging and returning exit code 2, so that path is not silent.
- **Directory scanning of unlisted extensions.** P1 now opens and parses every regular file in a scanned tree and treats any file containing GLOBAL, INST or STACK_GLOBAL opcodes as a pickle. This has three drawbacks:
  - Large unrelated files are read in full.
  - Binary files that happen to parse as pickle opcodes can be flagged as false positives or scan errors.
  - Exceptions other than `ValueError` or `OverflowError` from `genops` could abort the whole directory scan.
- **Remaining gaps.** Archive members in zip files are still selected by extension or magic bytes. Hugging Face files are still filtered by extension. Neither path is changed.

Overall, I do not think P1 reliably addresses the upstream vulnerability, and it adds a risky behaviour change.

## Verdict

```json
{"candidates": {"P1": {"removes_vulnerability": 0, "preserves_functionality": 0, "claim": 0, "confidence": 0.1, "evidence": [{"file": "src/picklescan/scanner.py", "line": 312, "quote": "        unsafe_filter = _unsafe_globals.get(g.module)"}, {"file": "src/picklescan/scanner.py", "line": 526, "quote": "            file_ext = os.path.splitext(file_name)[1]"}], "counterexample": "Failure-path bypasses are untouched: a zip member that raises zipfile.BadZipFile or RuntimeError is only logged as a warning in scan_zip_bytes, so its dangerous globals are never reported. Separately, directory scans now parse every regular file and may flag or choke on unrelated binary files."}}, "best": "none"}
```
