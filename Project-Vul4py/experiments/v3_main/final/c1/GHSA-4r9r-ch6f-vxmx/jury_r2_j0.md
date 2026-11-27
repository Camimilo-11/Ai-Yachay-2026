## Review

**P1** makes two changes:

- **Submodule wildcard matching.** `_build_scan_result_from_raw_globals` currently looks up rules by exact module name (`unsafe_filter = _unsafe_globals.get(g.module)`, line 312). P1 extends every `"*"` rule to dotted submodules.
- **Content sniffing in directory scans.** For local files with unlisted extensions, P1 runs `pickletools.genops` and scans the file if it finds `GLOBAL`, `INST` or `STACK_GLOBAL`.

Both changes are reasonable on their own, but the fix is incomplete. The maintainers' localization hint shows edits in the zip and 7z member selection, the Hugging Face scanner and the CLI. P1 says itself that "Remote model and archive member selection are unchanged", and the code confirms those paths still decide what to scan by extension or magic bytes.

**Hugging Face scanning is still extension-filtered** (`scan_huggingface_model`):
- Line 508 skips any file whose extension is not listed (`file_ext not in _zip_file_extensions`), via `continue` at line 512.
- The file is never fetched, so it never reaches `scan_bytes` at line 516.
- `_numpy_file_extensions` (`.npy`) is not in this list, nor is any renamed raw pickle.
- Concrete input: a repository containing `weights.npy` with an object dtype, whose embedded pickle is `cposix\nsystem\n(S'id'\ntR.`. Another input is the same pickle saved as `model.weights`.
- `picklescan -hf <repo>` never downloads either file. It reports 0 dangerous globals and returns exit code 0.
- `numpy.load(..., allow_pickle=True)` or `pickle.load` on those files would still run the payload.

**Zip member selection is unchanged** (`scan_zip_bytes`):
- A member is scanned only if `if file_ext in _pickle_file_extensions or any(` (line 392) matches, or the member starts with `\x80\x0N`, or it is NumPy.
- Concrete input: a zip containing a protocol‑0 pickle named `payload.txt`, with content `cposix\nsystem\n(S'id'\ntR.`. It has no `\x80` header and an unlisted extension, so it is silently skipped.
- P1 adds content sniffing for loose directory files only, not for archive members.
- The 7z path likewise extracts only `targets` filtered by `_pickle_file_extensions` (line 367).

**Fix is inconsistent across entry points.** The same renamed pickle is caught with `-p dir/` but missed with `-hf` or `-u`, or when it is inside an archive.

**Functionality:**
- The new directory pre-scan opens every regular file in the tree.
- A file that cannot be read now raises an exception, and the CLI turns that into "Unhandled exception" with exit code 2. Previously such files were skipped by extension.
- This is a minor regression. Otherwise the existing behaviour is preserved.

## Verdict
```json
{"candidates": {"P1": {"removes_vulnerability": 0, "preserves_functionality": 1, "claim": 0, "confidence": 0.12, "evidence": [{"file": "src/picklescan/scanner.py", "line": 508, "quote": "file_ext not in _zip_file_extensions"}, {"file": "src/picklescan/scanner.py", "line": 512, "quote": "continue"}, {"file": "src/picklescan/scanner.py", "line": 516, "quote": "scan_result.merge(scan_bytes(data, url, file_ext))"}, {"file": "src/picklescan/scanner.py", "line": 392, "quote": "if file_ext in _pickle_file_extensions or any("}, {"file": "src/picklescan/scanner.py", "line": 367, "quote": "targets = [f for f in file_names if f.endswith(tuple(_pickle_file_extensions))]"}, {"file": "src/picklescan/scanner.py", "line": 312, "quote": "unsafe_filter = _unsafe_globals.get(g.module)"}], "counterexample": "Hugging Face repo with file 'model.weights' (or object-dtype 'weights.npy') containing protocol-0 pickle b\"cposix\\nsystem\\n(S'id'\\ntR.\": scan_huggingface_model skips it by extension, so `picklescan -hf repo` reports 0 dangerous globals and exits 0. Likewise a zip with member 'payload.txt' holding the same protocol-0 pickle is skipped by scan_zip_bytes."}}, "best": "none"}
```
