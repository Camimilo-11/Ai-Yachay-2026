## Vulnerability

**Type:** Fail-open error handling in ZIP scanning (CWE-390, Detection of Error Condition Without Action). An attacker can hide a malicious pickle from the scanner and get a clean report.

**Location:** `src/picklescan/scanner.py`, function `scan_zip_bytes`, the `except` block at lines 405-409. The CLI exit-code logic is at `src/picklescan/cli.py` lines 84-86.

**Root cause:** `scan_zip_bytes` wraps the processing of every ZIP member in a `try`. The `except (zipfile.BadZipFile, RuntimeError)` handler only logs a warning and never marks the result as failed. `ScanResult.scan_err` defaults to `False`, so a member that cannot be read is silently dropped and the scan reports success. Elsewhere in the same file, a pickle parse error explicitly sets `scan_err=True`, so this path is inconsistent with the rest of the scanner. The CLI maps `scan_err` to exit code 2 and maps `issues_count == 0` to exit code 0, so a skipped member produces exit code 0.

**Exploit:** An attacker builds a ZIP (for example a PyTorch `.bin`/`.pt` archive) containing a malicious `data.pkl`. The member is made unreadable, for example by corrupting its CRC or setting its encryption flag. Per general `zipfile` behaviour, opening or reading it raises `BadZipFile` or `RuntimeError`. The handler swallows the exception, the member is never scanned, and the tool exits 0. A CI gate or model-hub check would then accept the file. I cannot see `relaxed_zipfile.py`, so I cannot confirm exactly which exceptions `RelaxedZipFile` raises for such members.

```json
{"evidence": [
  {"file": "src/picklescan/scanner.py", "line": 383, "quote": "with RelaxedZipFile(data, \"r\") as zip:"},
  {"file": "src/picklescan/scanner.py", "line": 388, "quote": "with zip.open(file_name, \"r\") as file:"},
  {"file": "src/picklescan/scanner.py", "line": 405, "quote": "except (zipfile.BadZipFile, RuntimeError) as e:"},
  {"file": "src/picklescan/scanner.py", "line": 406, "quote": "# Log decompression issues (password protected, corrupted, etc.)"},
  {"file": "src/picklescan/scanner.py", "line": 407, "quote": "_log.warning("},
  {"file": "src/picklescan/scanner.py", "line": 408, "quote": "\"Invalid file %s in zip archive %s: %s\", file_name, file_id, str(e)"},
  {"file": "src/picklescan/scanner.py", "line": 44, "quote": "scan_err: bool = False"},
  {"file": "src/picklescan/scanner.py", "line": 345, "quote": "e.globals, file_id, scan_err=True"},
  {"file": "src/picklescan/cli.py", "line": 84, "quote": "if scan_result.scan_err:"},
  {"file": "src/picklescan/cli.py", "line": 86, "quote": "return 0 if scan_result.issues_count == 0 else 1"}
]}
```

## Fix

The patch sets `result.scan_err = True` in the ZIP member exception handler, before the warning is logged. A member that cannot be read is then reported as a scan error. The CLI already returns exit code 2 for `scan_err`, which blocks the file in the same way as a parse failure. This matches how `scan_pickle_bytes` already handles unparseable pickles (line 345).

Existing behaviour is preserved for every case that is not an error. Valid archives, pickle detections, and globals reporting are untouched. The only change is that an unreadable member now sets the error flag, which the code already supports. No tests are edited.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -405,5 +405,6 @@ def scan_zip_bytes(data: IO[bytes], file_id) -> ScanResult:
             except (zipfile.BadZipFile, RuntimeError) as e:
                 # Log decompression issues (password protected, corrupted, etc.)
+                result.scan_err = True
                 _log.warning(
                     "Invalid file %s in zip archive %s: %s", file_name, file_id, str(e)
                 )
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.6}
```

Confidence is moderate because `relaxed_zipfile.py` is not visible, so I cannot confirm which exceptions reach the handler. The hidden tests might also expect a different error path or exit code for corrupt ZIPs.
