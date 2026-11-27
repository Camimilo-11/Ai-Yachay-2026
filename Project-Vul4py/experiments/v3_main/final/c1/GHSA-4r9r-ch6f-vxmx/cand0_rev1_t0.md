## Vulnerability

**CWE-184: Incomplete List of Disallowed Inputs.** `src/picklescan/scanner.py` looks up denylist rules by exact module name. A `*` rule marks every global in the listed module as dangerous, but does not cover its submodules. An attacker-controlled pickle can reference a global through a submodule and avoid a dangerous finding if no separate rule matches.

**CWE-693: Protection Mechanism Failure.** The local directory scanner skips files with unlisted extensions before reading their contents. Renaming a raw pickle can therefore prevent it from being scanned at all. In either case, if there are no other findings or scan errors, the CLI can exit successfully without a dangerous finding.

```json
{"evidence":[{"file":"src/picklescan/scanner.py","line":120,"quote":"    \"asyncio\": \"*\","},{"file":"src/picklescan/scanner.py","line":234,"quote":"            for op in pickletools.genops(data):"},{"file":"src/picklescan/scanner.py","line":252,"quote":"                globals.add(tuple(op_value.split(\" \", 1)))"},{"file":"src/picklescan/scanner.py","line":312,"quote":"        unsafe_filter = _unsafe_globals.get(g.module)"},{"file":"src/picklescan/scanner.py","line":320,"quote":"            unsafe_filter == \"*\" or g.name in unsafe_filter"},{"file":"src/picklescan/scanner.py","line":326,"quote":"            issues_count += 1"},{"file":"src/picklescan/scanner.py","line":330,"quote":"            g.safety = SafetyLevel.Suspicious"},{"file":"src/picklescan/scanner.py","line":524,"quote":"    for base_path, _, file_names in os.walk(path):"},{"file":"src/picklescan/scanner.py","line":526,"quote":"            file_ext = os.path.splitext(file_name)[1]"},{"file":"src/picklescan/scanner.py","line":527,"quote":"            if ("},{"file":"src/picklescan/scanner.py","line":528,"quote":"                file_ext not in _zip_file_extensions"},{"file":"src/picklescan/scanner.py","line":529,"quote":"                and file_ext not in _pickle_file_extensions"},{"file":"src/picklescan/scanner.py","line":530,"quote":"                and file_ext not in _pytorch_file_extensions"},{"file":"src/picklescan/scanner.py","line":532,"quote":"                continue"},{"file":"src/picklescan/scanner.py","line":536,"quote":"                scan_result.merge(scan_bytes(file, file_path, file_ext))"},{"file":"src/picklescan/cli.py","line":83,"quote":"        if scan_result.scan_err:"},{"file":"src/picklescan/cli.py","line":85,"quote":"        return 0 if scan_result.issues_count == 0 else 1"}]}
```

## Fix

Apply existing wildcard rules at dotted module boundaries so they cover submodules without matching unrelated names. Keep named rules unchanged; broadening the `torch._inductor.codecache` rule would not fix either reported bypass.

Keep the existing scan path for recognized extensions. For other regular files in a local directory, statically check for pickle global opcodes without unpickling. If one is found, rewind the stream and send it through the normal scanner. This catches renamed raw pickles, including ones without a protocol header, without treating every unrelated file as a failed scan. Remote model and archive member selection are unchanged.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -309,7 +309,12 @@
     for rg in raw_globals:
         g = Global(rg[0], rg[1], SafetyLevel.Dangerous)
         safe_filter = _safe_globals.get(g.module)
         unsafe_filter = _unsafe_globals.get(g.module)
+        if unsafe_filter != "*" and any(
+            rule == "*" and g.module.startswith(module + ".")
+            for module, rule in _unsafe_globals.items()
+        ):
+            unsafe_filter = "*"
         if "unknown" in g.module or "unknown" in g.name:
             g.safety = SafetyLevel.Dangerous
             _log.warning(
@@ -518,21 +523,37 @@
     return scan_result
 
 
+def _has_pickle_globals(data: IO[bytes]) -> bool:
+    start = data.tell()
+    try:
+        while True:
+            for opcode, _, _ in pickletools.genops(data):
+                if opcode.name in ("GLOBAL", "INST", "STACK_GLOBAL"):
+                    return True
+    except (ValueError, OverflowError):
+        return False
+    finally:
+        data.seek(start)
+
+
 def scan_directory_path(path) -> ScanResult:
     scan_result = ScanResult([])
 
     for base_path, _, file_names in os.walk(path):
         for file_name in file_names:
             file_ext = os.path.splitext(file_name)[1]
-            if (
-                file_ext not in _zip_file_extensions
-                and file_ext not in _pickle_file_extensions
-                and file_ext not in _pytorch_file_extensions
-            ):
-                continue
+            supported_ext = (
+                file_ext in _zip_file_extensions
+                or file_ext in _pickle_file_extensions
+                or file_ext in _pytorch_file_extensions
+            )
             file_path = os.path.join(base_path, file_name)
-            _log.debug("Scanning file %s", file_path)
+            if not supported_ext and not os.path.isfile(file_path):
+                continue
             with open(file_path, "rb") as file:
+                if not supported_ext and not _has_pickle_globals(file):
+                    continue
+                _log.debug("Scanning file %s", file_path)
                 scan_result.merge(scan_bytes(file, file_path, file_ext))
 
     return scan_result
```

## Self-assessment

```json
{"claim":1,"confidence":0.86}
```
