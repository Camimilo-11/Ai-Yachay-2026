## Vulnerability

- **Type:** Incomplete denylist (CWE-184, Incomplete List of Disallowed Inputs), which allows dangerous-global detection bypass (CWE-693 is the closest protection-mechanism failure).
- **Location:** `src/picklescan/scanner.py`. The denylist `_unsafe_globals` is at lines 100-158, and the classification that consults it is in `_build_scan_result_from_raw_globals` at lines 300-312. The localization hint lines 136, 140 and 155 are existing entries in this denylist (`"sys"`, `"pip"`, and the `torch.utils.data.datapipes.utils.decoder` entry). I did not find a change at those lines that clearly matches the hint, so this is my best reading rather than a confirmed match.
- **Root cause:** The scanner marks a global as `Dangerous` only if its module is in `_unsafe_globals` and the name matches. Anything else falls through to `Suspicious`. Only `Dangerous` results increment `issues_count`, so a `Suspicious` global does not count as an issue.
- **Exploit:** A pickle that references a code-executing function in a module that is not in the denylist would be classified `Suspicious` and reported with `issues_count` of 0. The modules I have in mind are `cProfile`, `profile` and `pty`. This is based on general Python knowledge of their stdlib functions, not on anything in the shown files, and I have not verified it by running code.

```json
{"evidence": [
  {"file": "src/picklescan/scanner.py", "line": 140, "quote": "\"pip\": \"*\","},
  {"file": "src/picklescan/scanner.py", "line": 141, "quote": "\"pydoc\": \"pipepager\",  # pydoc.pipepager('help','echo pwned')"},
  {"file": "src/picklescan/scanner.py", "line": 300, "quote": "unsafe_filter = _unsafe_globals.get(g.module)"},
  {"file": "src/picklescan/scanner.py", "line": 305, "quote": "elif unsafe_filter is not None and (unsafe_filter == \"*\" or g.name in unsafe_filter):"},
  {"file": "src/picklescan/scanner.py", "line": 312, "quote": "g.safety = SafetyLevel.Suspicious"}
]}
```

## Fix

The patch adds `cProfile`, `profile` and `pty` to `_unsafe_globals` with `"*"`, so any global from those modules is classified `Dangerous` and counted as an issue. This is a denylist addition only. Existing entries and the classification logic are unchanged. The only behavioural change is that globals from these three modules, which are not expected in legitimate model pickles, are now flagged.

I have not verified that these three modules are the intended target, so this is a partial fix for the denylist gap and not a confirmed fix for the reported vulnerability.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -138,6 +138,9 @@
     "pickle": "*",
     "_pickle": "*",
     "pip": "*",
+    "profile": "*",  # profile.run() executes a string statement
+    "cProfile": "*",  # cProfile.run() executes a string statement
+    "pty": "*",  # pty.spawn() runs a shell command
     "pydoc": "pipepager",  # pydoc.pipepager('help','echo pwned')
     "timeit": "*",
     "torch._dynamo.guards": {"GuardBuilder.get"},
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.25}
```
