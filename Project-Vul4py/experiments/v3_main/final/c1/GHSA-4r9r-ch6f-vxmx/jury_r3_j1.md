## Review

### P1

**Wildcard submodule matching.** This part is sound. The lookup at `scanner.py:312` (`unsafe_filter = _unsafe_globals.get(g.module)`) is an exact-match lookup, so a global like `asyncio.subprocess Popen` is only `Suspicious`. P1's `startswith(module + ".")` check marks it `Dangerous`.

**The other reviewer's "infinite loop" claim is wrong, so I do not adopt it.**
- `pickletools.genops` raises `ValueError("pickle exhausted before seeing STOP")` when it reads `b""`.
- An empty file therefore raises on the first call. A pickle with no globals ends at STOP, and the next outer iteration hits EOF and raises the same `ValueError`.
- Each outer iteration consumes bytes, and `except (ValueError, OverflowError): return False` terminates the loop.
- I accept the cosmetic `while True` oddity, but it does not hang.

**Real functional regression: false positives.**
- For files with an unlisted extension, P1 runs `_has_pickle_globals`, which returns `True` on any `GLOBAL` opcode (`c`).
- A plain text file such as a Python source file starting `class Foo:\n    pass\n` parses as `c` plus two lines of text, which `genops` accepts as a GLOBAL. The same happens with a README starting with "c" and two lines.
- `scan_bytes` then calls `scan_pickle_bytes` on it. The scan hits a parse error, and the error path in `scan_pickle_bytes` returns `scan_err=True` (`ScanResult([], scan_err=True)`, or a result built with `scan_err=True` when globals were found).
- `cli.py:83` (`if scan_result.scan_err:`) then returns 2.
- Directories that previously scanned clean (exit 0) now fail with exit 2 whenever they contain such files. P1's own text says the rewind-and-scan approach avoids "treating every unrelated file as a failed scan", but it does not.

**Further regressions.** `open(file_path, "rb")` is now called on every regular file, so an unreadable unsupported file raises and the CLI returns 2 (`Unhandled exception`). Sniffing also reads every file in the tree, which is slow on large trees.

**Incomplete coverage (conceded).**
- `scan_zip_bytes` still selects members only by extension or `\x80\x0N` magic (`scanner.py:392`).
- `scan_huggingface_model` still skips unlisted extensions (`scanner.py:508`, `continue` at line 512).
- A zip member `payload.txt` containing `cposix\nsystem\n(S'id'\ntR.` is still skipped.
- `.npy` is not in the Hugging Face filter either, so an object-dtype `weights.npy` is never fetched there.
- These bypasses remain, so the vulnerability is only partially removed.

## Verdict

```json
{"candidates": {"P1": {"removes_vulnerability": 0, "preserves_functionality": 0, "claim": 0, "confidence": 0.05, "evidence": [{"file": "src/picklescan/scanner.py", "line": 392, "quote": "if file_ext in _pickle_file_extensions or any("}, {"file": "src/picklescan/scanner.py", "line": 508, "quote": "file_ext not in _zip_file_extensions"}, {"file": "src/picklescan/cli.py", "line": 83, "quote": "if scan_result.scan_err:"}], "counterexample": "A zip containing payload.txt with b\"cposix\\nsystem\\n(S'id'\\ntR.\" is still skipped. A HF repo with model.weights holding the same pickle is never downloaded. Separately, a directory containing notes.txt starting 'class Foo:\\n    pass\\n' is sniffed as GLOBAL, scanned, hits a parse error, sets scan_err and the CLI exits 2 instead of 0."}}, "best": "none"}
```
