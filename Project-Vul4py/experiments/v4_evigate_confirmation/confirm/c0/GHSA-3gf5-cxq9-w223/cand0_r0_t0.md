## Vulnerability

**CWE-184: Incomplete list of disallowed inputs.** In `src/picklescan/scanner.py`, several unsafe-module rules list only specific member names. The scanner extracts module and member names from the input pickle, but an unlisted member can fall through to `Suspicious` without incrementing `issues_count`. An attacker can use an unlisted execution-capable reference from one of these modules to evade a dangerous finding. A caller that treats zero issues as approval could then pass the pickle to a deserializer.

```json
{
  "evidence": [
    {"file": "src/picklescan/scanner.py", "line": 250, "quote": "            for op in pickletools.genops(data):"},
    {"file": "src/picklescan/scanner.py", "line": 268, "quote": "                globals.add(tuple(op_value.split(\" \", 1)))"},
    {"file": "src/picklescan/scanner.py", "line": 137, "quote": "    \"code\": {\"InteractiveInterpreter.runcode\"},"},
    {"file": "src/picklescan/scanner.py", "line": 138, "quote": "    \"idlelib.autocomplete\": {\"AutoComplete.get_entity\", \"AutoComplete.fetch_completions\"},"},
    {"file": "src/picklescan/scanner.py", "line": 139, "quote": "    \"idlelib.calltip\": {\"Calltip.fetch_tip\", \"get_entity\"},"},
    {"file": "src/picklescan/scanner.py", "line": 140, "quote": "    \"idlelib.debugobj\": {\"ObjectTreeItem.SetText\"},"},
    {"file": "src/picklescan/scanner.py", "line": 141, "quote": "    \"lib2to3.pgen2.grammar\": {\"Grammar.loads\"},"},
    {"file": "src/picklescan/scanner.py", "line": 157, "quote": "    \"torch.utils.bottleneck.__main__\": {\"run_cprofile\"},"},
    {"file": "src/picklescan/scanner.py", "line": 324, "quote": "        unsafe_filter = _unsafe_globals.get(g.module)"},
    {"file": "src/picklescan/scanner.py", "line": 329, "quote": "        elif unsafe_filter is not None and (unsafe_filter == \"*\" or g.name in unsafe_filter):"},
    {"file": "src/picklescan/scanner.py", "line": 332, "quote": "            issues_count += 1"},
    {"file": "src/picklescan/scanner.py", "line": 336, "quote": "            g.safety = SafetyLevel.Suspicious"}
  ]
}
```

## Fix

Use the existing `*` rule for the six affected modules. Every reference from those exact modules now takes the dangerous branch, including references that were already flagged. Pickle parsing, result reporting, and rules for other modules remain unchanged.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -134,11 +134,11 @@
     "ssl": "*",  # DNS exfiltration via ssl.get_server_certificate()
     "subprocess": "*",
     "sys": "*",
-    "code": {"InteractiveInterpreter.runcode"},
-    "idlelib.autocomplete": {"AutoComplete.get_entity", "AutoComplete.fetch_completions"},
-    "idlelib.calltip": {"Calltip.fetch_tip", "get_entity"},
-    "idlelib.debugobj": {"ObjectTreeItem.SetText"},
-    "lib2to3.pgen2.grammar": {"Grammar.loads"},
+    "code": "*",
+    "idlelib.autocomplete": "*",
+    "idlelib.calltip": "*",
+    "idlelib.debugobj": "*",
+    "lib2to3.pgen2.grammar": "*",
     "pdb": "*",
     "pickle": "*",
     "_pickle": "*",
@@ -154,7 +154,7 @@
     "torch.utils._config_module": {
         "ConfigModule.load_config"
     },  # allows storing a pickle inside a pickle (if this has valid use cases, scan the input bytes instead of flagging the global)
-    "torch.utils.bottleneck.__main__": {"run_cprofile"},
+    "torch.utils.bottleneck.__main__": "*",
     "torch.utils.collect_env": {"run"},
     "torch.utils.data.datapipes.utils.decoder": {
         "basichandlers"
```

## Self-assessment

```json
{
  "claim": 1,
  "confidence": 0.8
}
```
