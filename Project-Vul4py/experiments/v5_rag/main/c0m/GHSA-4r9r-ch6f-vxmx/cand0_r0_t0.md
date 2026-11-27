## Vulnerability

**Type:** Fail-open error handling in archive scanning. This is closest to CWE-390 (Detection of Error Condition Without Action) and CWE-754 (Improper Check for Unusual or Exceptional Conditions), which can let a malicious payload evade detection.

**Location:** `src/picklescan/scanner.py`, function `scan_zip_bytes`, the `except` handler for each zip member (lines 405-409).

**Root cause:** `scan_zip_bytes` iterates over every member of a zip archive. If reading a member raises `zipfile.BadZipFile` or `RuntimeError`, the handler only logs a warning and continues. It never sets `result.scan_err`, so the returned `ScanResult` looks like a clean scan. The `merge` method propagates `scan_err` upward, and `cli.main` returns exit code 2 only when `scan_err` is set. A member that could not be inspected is therefore reported as "0 issues, exit 0".

**Exploit scenario:** An attacker packages a malicious pickle inside a zip-based model file (a `.zip`, `.npz`, or PyTorch zip checkpoint). The member is made unreadable through the standard zip errors that the handler catches. For example, the member might be encrypted (which the standard library reports as `RuntimeError`) or structurally corrupted (which it reports as `BadZipFile`). picklescan skips that member, logs only a warning, and reports the archive as clean with exit code 0. A CI gate or a user relying on the exit status accepts the file. Whether a downstream loader can still execute the member depends on that loader. I cannot see `relaxed_zipfile.py`, so I cannot confirm which exact conditions it suppresses or raises.

```json
{"evidence": [
  {"file": "src/picklescan/scanner.py", "line": 383, "quote": "with RelaxedZipFile(data, \"r\") as zip:"},
  {"file": "src/picklescan/scanner.py", "line": 384, "quote": "file_names = zip.namelist()"},
  {"file": "src/picklescan/scanner.py", "line": 388, "quote": "with zip.open(file_name, \"r\") as file:"},
  {"file": "src/picklescan/scanner.py", "line": 405, "quote": "except (zipfile.BadZipFile, RuntimeError) as e:"},
  {"file": "src/picklescan/scanner.py", "line": 406, "quote": "# Log decompression issues (password protected, corrupted, etc.)"},
  {"file": "src/picklescan/scanner.py", "line": 407, "quote": "_log.warning("},
  {"file": "src/picklescan/scanner.py", "line": 408, "quote": "\"Invalid file %s in zip archive %s: %s\", file_name, file_id, str(e)"},
  {"file": "src/picklescan/scanner.py", "line": 51, "quote": "self.scan_err = self.scan_err or sr.scan_err"},
  {"file": "src/picklescan/cli.py", "line": 84, "quote": "if scan_result.scan_err:"},
  {"file": "src/picklescan/cli.py", "line": 85, "quote": "return 2"}
]}
```

## Fix

The patch adds `result.scan_err = True` to the zip-member `except` handler. The handler keeps its warning log and keeps scanning the remaining members. The only change is that an uninspectable member now marks the archive as a scan error. That error flows through `ScanResult.merge` (scanner.py line 51) into the top-level result, and the CLI returns exit code 2 (cli.py lines 84-85). The scan now fails closed instead of reporting a false clean result.

Existing behaviour is preserved for all archives that scan successfully. Issue counts, globals, and the warning message are unchanged. The only observable difference is for archives that contain unreadable members, which should not have been reported as clean. I could not run the test suite. Any existing test that expects exit code 0 for such an archive would need updating, and I was not permitted to change tests.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -405,7 +405,8 @@ def scan_zip_bytes(data: IO[bytes], file_id) -> ScanResult:
             except (zipfile.BadZipFile, RuntimeError) as e:
                 # Log decompression issues (password protected, corrupted, etc.)
                 _log.warning(
                     "Invalid file %s in zip archive %s: %s", file_name, file_id, str(e)
                 )
+                result.scan_err = True
 
     return result
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.5}
```
