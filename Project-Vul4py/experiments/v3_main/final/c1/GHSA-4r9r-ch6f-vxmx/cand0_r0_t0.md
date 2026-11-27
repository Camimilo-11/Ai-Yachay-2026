## Vulnerability

**CWE-184: Incomplete List of Disallowed Inputs.** In `src/picklescan/scanner.py`, the denylist for `torch._inductor.codecache` specifies only `compile_file`. An attacker-controlled pickle that references another global in that module can receive a `Suspicious` classification instead of a `Dangerous` finding. That reference does not increment the issue count, so a caller relying on a zero issue count can accept the file.

```json
{"evidence": [{"file": "src/picklescan/scanner.py", "line": 143, "quote": "    \"torch._inductor.codecache\": \"compile_file\",  # compile_file('', '', ['sh', '-c','$(echo pwned)'])"}, {"file": "src/picklescan/scanner.py", "line": 234, "quote": "            for op in pickletools.genops(data):"}, {"file": "src/picklescan/scanner.py", "line": 252, "quote": "                globals.add(tuple(op_value.split(\" \", 1)))"}, {"file": "src/picklescan/scanner.py", "line": 312, "quote": "        unsafe_filter = _unsafe_globals.get(g.module)"}, {"file": "src/picklescan/scanner.py", "line": 320, "quote": "            unsafe_filter == \"*\" or g.name in unsafe_filter"}, {"file": "src/picklescan/scanner.py", "line": 326, "quote": "            issues_count += 1"}, {"file": "src/picklescan/scanner.py", "line": 330, "quote": "            g.safety = SafetyLevel.Suspicious"}]}
```

## Fix

Use the existing `*` denylist rule for `torch._inductor.codecache`. Every global from that module now follows the same dangerous-classification and issue-counting path as `compile_file`. The patch changes only that module’s classification policy; parsing, reporting, and rules for other modules are unchanged.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -140,7 +140,7 @@
     "pip": "*",
     "pydoc": "pipepager",  # pydoc.pipepager('help','echo pwned')
     "timeit": "*",
-    "torch._inductor.codecache": "compile_file",  # compile_file('', '', ['sh', '-c','$(echo pwned)'])
+    "torch._inductor.codecache": "*",
     "torch.serialization": "load",  # pickle could be used to load a different file
     "venv": "*",
     "webbrowser": "*",  # Includes webbrowser.open()
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.85}
```
