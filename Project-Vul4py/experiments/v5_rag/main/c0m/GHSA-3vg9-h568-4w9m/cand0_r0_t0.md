## Vulnerability

**Type:** Incomplete denylist / detection bypass (CWE-184, Incomplete List of Disallowed Inputs). I'm not certain this is the intended vulnerability; see the localization note below.

**Location:** `src/picklescan/scanner.py`. `STACK_GLOBAL` names are extracted at line 292 and classified in `_build_scan_result_from_raw_globals` (lines 316–330).

**Root cause:** The denylist is keyed only on `g.module`, the module string (line 318). For a `STACK_GLOBAL` opcode, the scanner takes the name string verbatim from the pickle (line 287) and never splits it on `.`. A dotted name such as `os.system` is therefore compared as a single string against the module's filter. Its name never matches `"*"`-style module entries, and it is not checked against any dotted path. A reference whose module is not in the denylist (for example `posixpath`) and whose name is `os.system` is classified as `Suspicious` (line 330). `Suspicious` does not increment `issues_count` (only the unknown and unsafe branches do, lines 319–322), so the file is reported clean.

**Localization note:** The hint points at `_unsafe_globals` lines 136, 140 and 155 (`"sys": "*",`, `"pip": "*",`, and the `basichandlers` entry). I read those entries and did not find a defect in them. The bypass above is in the lookup logic, not in those entries. If the intended vulnerability is elsewhere, this patch will not address it.

**Exploit sketch:** A protocol-4 pickle pushes `"posixpath"` and `"os.system"` as strings, emits `STACK_GLOBAL`, then calls the resulting callable with `"echo pwned"` via `REDUCE`. The scanner reports no issues. This relies on CPython behaviour outside the shown files: for protocol ≥ 4, `pickle` resolves dotted `STACK_GLOBAL` names through attribute access, and `posixpath` has `os` as a module attribute. I have not verified this against the stdlib source.

```json
{"evidence": [
  {"file": "src/picklescan/scanner.py", "line": 100, "quote": "_unsafe_globals = {"},
  {"file": "src/picklescan/scanner.py", "line": 136, "quote": "\"sys\": \"*\","},
  {"file": "src/picklescan/scanner.py", "line": 154, "quote": "\"basichandlers\""},
  {"file": "src/picklescan/scanner.py", "line": 287, "quote": "values.append(ops[n - offset][1])"},
  {"file": "src/picklescan/scanner.py", "line": 292, "quote": "globals.add((values[1], values[0]))"},
  {"file": "src/picklescan/scanner.py", "line": 316, "quote": "g = Global(rg[0], rg[1], SafetyLevel.Dangerous)"},
  {"file": "src/picklescan/scanner.py", "line": 318, "quote": "unsafe_filter = _unsafe_globals.get(g.module)"},
  {"file": "src/picklescan/scanner.py", "line": 323, "quote": "elif unsafe_filter is not None and (unsafe_filter == \"*\" or g.name in unsafe_filter):"},
  {"file": "src/picklescan/scanner.py", "line": 330, "quote": "g.safety = SafetyLevel.Suspicious"}
]}
```

## Fix

The patch adds `_is_unsafe_dotted_name(name)`. It returns true when a dotted name contains a path segment that names a denylisted module with `"*"` (for example `os` in `os.system`). In `_build_scan_result_from_raw_globals`, such names are classified as `Dangerous` through the existing unsafe branch.

- **Why it closes the bypass:** `posixpath` + `os.system` now produces `Dangerous` and increments `issues_count`.
- **Why behaviour is otherwise preserved:** Non-dotted names are unaffected because the helper requires a `.`. Dotted names with no denylisted-module segment keep their previous classification. The unknown-opcode check still runs first, and the safe-list path is unchanged.

**Limitations:** This is a partial fix. Aliases whose segment is not a denylisted module name (for example `tempfile._os.system`) are still not caught. Closing that class fully would require resolving attribute chains, which a static scanner cannot do without importing modules.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -305,4 +305,10 @@
     return globals
 
 
+def _is_unsafe_dotted_name(name: str) -> bool:
+    # Protocol 4+ STACK_GLOBAL names may be dotted attribute paths resolved at load time,
+    # e.g. module "posixpath" + name "os.system" reaches os.system. Flag paths containing an unsafe module.
+    return "." in name and any(_unsafe_globals.get(part) == "*" for part in name.split("."))
+
+
 def _build_scan_result_from_raw_globals(
     raw_globals: Set[Tuple[str, str]],
     file_id,
@@ -320,7 +326,7 @@
             g.safety = SafetyLevel.Dangerous
             _log.warning("%s: %s import '%s %s' FOUND", file_id, g.safety.value, g.module, g.name)
             issues_count += 1
-        elif unsafe_filter is not None and (unsafe_filter == "*" or g.name in unsafe_filter):
+        elif _is_unsafe_dotted_name(g.name) or (unsafe_filter is not None and (unsafe_filter == "*" or g.name in unsafe_filter)):
             g.safety = SafetyLevel.Dangerous
             _log.warning("%s: %s import '%s %s' FOUND", file_id, g.safety.value, g.module, g.name)
             issues_count += 1
```

## Self-assessment

```json
{"claim": 1, "confidence": 0.35}
```
