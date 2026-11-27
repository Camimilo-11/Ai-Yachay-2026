## Vulnerability

**CWE-184: Incomplete denylist.** `src/picklescan/scanner.py` flags `torch.serialization.load` but omits the top-level `torch.load` entry point, which the file identifies as another way to load a pickle. The scanner matches globals by exact module name, so a pickle that references `torch.load` can be classified as suspicious without increasing the issue count. If the scan completes without errors or other findings, the CLI returns exit code `0`.

```json
{"evidence":[{"file":"src/picklescan/scanner.py","line":144,"quote":"    \"torch.serialization\": \"load\",  # pickle could be used to load a different file"},{"file":"src/picklescan/scanner.py","line":160,"quote":"# torch.load()"},{"file":"src/picklescan/scanner.py","line":234,"quote":"            for op in pickletools.genops(data):"},{"file":"src/picklescan/scanner.py","line":252,"quote":"                globals.add(tuple(op_value.split(\" \", 1)))"},{"file":"src/picklescan/scanner.py","line":312,"quote":"        unsafe_filter = _unsafe_globals.get(g.module)"},{"file":"src/picklescan/scanner.py","line":320,"quote":"            unsafe_filter == \"*\" or g.name in unsafe_filter"},{"file":"src/picklescan/scanner.py","line":326,"quote":"            issues_count += 1"},{"file":"src/picklescan/scanner.py","line":327,"quote":"        elif safe_filter is not None and (safe_filter == \"*\" or g.name in safe_filter):"},{"file":"src/picklescan/scanner.py","line":330,"quote":"            g.safety = SafetyLevel.Suspicious"},{"file":"src/picklescan/cli.py","line":84,"quote":"        if scan_result.scan_err:"},{"file":"src/picklescan/cli.py","line":86,"quote":"        return 0 if scan_result.issues_count == 0 else 1"}]}
```

## Fix

Add an exact denylist entry for `torch.load`. It now counts as a dangerous global, while other `torch` globals continue through the existing classification rules.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -140,6 +140,7 @@
     "pip": "*",
     "pydoc": "pipepager",  # pydoc.pipepager('help','echo pwned')
     "timeit": "*",
+    "torch": {"load"},
     "torch._inductor.codecache": "compile_file",  # compile_file('', '', ['sh', '-c','$(echo pwned)'])
     "torch.serialization": "load",  # pickle could be used to load a different file
     "venv": "*",
```

## Self-assessment

```json
{"claim":1,"confidence":0.88}
```
