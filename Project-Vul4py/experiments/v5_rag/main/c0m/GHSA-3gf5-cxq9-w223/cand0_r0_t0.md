## Vulnerability

**Type:** CWE-184 (Incomplete List of Disallowed Inputs), suspected. I could not confirm this from the shown code alone.

**Location:** The `_unsafe_globals` blocklist in `src/picklescan/scanner.py`. The localization hint points to lines 136-141 and 157. Within that region, the entries at lines 137 and 157 are name-restricted sets rather than `"*"` wildcards.

**Root cause:** The scanner classifies a pickle global as Dangerous only if its name is in the module's listed set. A global that is not listed falls through to the default and is classified as Suspicious, which does not count as an issue. Line 137 lists only `InteractiveInterpreter.runcode` for the `code` module. Line 157 lists only `run_cprofile` for `torch.utils.bottleneck.__main__`.

**Exploitation:** An attacker who crafts a pickle that references an unlisted function in one of these modules would receive a Suspicious rating, with no issue counted and no infected file flagged. Whether the unlisted names (for example, `code.InteractiveInterpreter.runsource` or `torch.utils.bottleneck.__main__.run_autograd_prof`) actually execute code is general Python and PyTorch knowledge. It is not visible in the shown files and I have not verified it. The attack is therefore plausible but unconfirmed.

Evidence for the code paths shown in the files:
- Untrusted pickle bytes are disassembled with `pickletools.genops(data)`.
- Module and name pairs are collected from STACK_GLOBAL.
- Classification checks membership in the unsafe set, and the default is Suspicious.

```json
{"evidence": [
  {"file": "src/picklescan/scanner.py", "line": 137, "quote": "\"code\": {\"InteractiveInterpreter.runcode\"},"},
  {"file": "src/picklescan/scanner.py", "line": 157, "quote": "\"torch.utils.bottleneck.__main__\": {\"run_cprofile\"},"},
  {"file": "src/picklescan/scanner.py", "line": 250, "quote": "for op in pickletools.genops(data):"},
  {"file": "src/picklescan/scanner.py", "line": 298, "quote": "globals.add((values[1], values[0]))"},
  {"file": "src/picklescan/scanner.py", "line": 329, "quote": "elif unsafe_filter is not None and (unsafe_filter == \"*\" or g.name in unsafe_filter):"},
  {"file": "src/picklescan/scanner.py", "line": 336, "quote": "g.safety = SafetyLevel.Suspicious"}
]}
```

## Fix

The patch adds two qualified names to the existing set-valued blocklist entries:
- `InteractiveInterpreter.runsource` to the `code` entry, alongside `InteractiveInterpreter.runcode`.
- `run_autograd_prof` to the `torch.utils.bottleneck.__main__` entry, alongside `run_cprofile`.

These names are inferred from my general knowledge of the standard library and PyTorch, not from the shown files. The change only moves these exact globals from Suspicious to Dangerous. It leaves the classification of every other global, the safe-globals table, and the scanning logic unchanged. It should therefore not break existing behaviour, except for tests that assert Suspicious for these two exact names.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -134,7 +134,7 @@
     "ssl": "*",  # DNS exfiltration via ssl.get_server_certificate()
     "subprocess": "*",
     "sys": "*",
-    "code": {"InteractiveInterpreter.runcode"},
+    "code": {"InteractiveInterpreter.runcode", "InteractiveInterpreter.runsource"},
     "idlelib.autocomplete": {"AutoComplete.get_entity", "AutoComplete.fetch_completions"},
     "idlelib.calltip": {"Calltip.fetch_tip", "get_entity"},
     "idlelib.debugobj": {"ObjectTreeItem.SetText"},
@@ -156,4 +156,4 @@
     },  # allows storing a pickle inside a pickle (if this has valid use cases, scan the input bytes instead of flagging the global)
-    "torch.utils.bottleneck.__main__": {"run_cprofile"},
+    "torch.utils.bottleneck.__main__": {"run_cprofile", "run_autograd_prof"},
     "torch.utils.collect_env": {"run"},
     "torch.utils.data.datapipes.utils.decoder": {
```

## Self-assessment

```json
{"claim": 0, "confidence": 0.2}
```
