## Vulnerability

**CWE-184: Incomplete list of disallowed inputs.** The scanner classifies pickle globals by their exact module name. Its denylist covers `torch.serialization.load` but omits `torch.load`, the public name for the same loader. An attacker can reference the public name so the scanner classifies the loader as suspicious rather than dangerous. If the scan finds no other issues and completes without error, the CLI can exit successfully.

```json
{
  "evidence": [
    {"file": "src/picklescan/scanner.py", "line": 252, "quote": "                globals.add(tuple(op_value.split(\" \", 1)))"},
    {"file": "src/picklescan/scanner.py", "line": 144, "quote": "    \"torch.serialization\": \"load\",  # pickle could be used to load a different file"},
    {"file": "src/picklescan/scanner.py", "line": 160, "quote": "# torch.load()"},
    {"file": "src/picklescan/scanner.py", "line": 312, "quote": "        unsafe_filter = _unsafe_globals.get(g.module)"},
    {"file": "src/picklescan/scanner.py", "line": 320, "quote": "            unsafe_filter == \"*\" or g.name in unsafe_filter"},
    {"file": "src/picklescan/scanner.py", "line": 326, "quote": "            issues_count += 1"},
    {"file": "src/picklescan/scanner.py", "line": 330, "quote": "            g.safety = SafetyLevel.Suspicious"},
    {"file": "src/picklescan/cli.py", "line": 84, "quote": "        if scan_result.scan_err:"},
    {"file": "src/picklescan/cli.py", "line": 86, "quote": "        return 0 if scan_result.issues_count == 0 else 1"}
  ]
}
```

## Fix

Add `load` to the denylist for the `torch` module. Both names now match the existing dangerous-global check, without changing how any other `torch` global is classified.

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
{
  "claim": 1,
  "confidence": 0.91
}
```
