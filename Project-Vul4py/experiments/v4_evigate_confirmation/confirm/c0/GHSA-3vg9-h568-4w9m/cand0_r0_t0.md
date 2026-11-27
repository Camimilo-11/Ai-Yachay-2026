## Vulnerability

**CWE-184: Incomplete list of disallowed inputs.** In `src/picklescan/scanner.py`, the scanner looks up unsafe globals by exact module name. It marks `torch.serialization.load` as dangerous but omits `torch.load`, even though the source identifies it as a loader that can open another pickle file. A crafted pickle that references `torch.load` alone is therefore reported as suspicious without incrementing the issue count. This can hide a second-stage pickle from consumers that rely on the dangerous-issue count.

```json
{"evidence":[{"file":"src/picklescan/scanner.py","line":243,"quote":"            for op in pickletools.genops(data):"},{"file":"src/picklescan/scanner.py","line":261,"quote":"                globals.add(tuple(op_value.split(\" \", 1)))"},{"file":"src/picklescan/scanner.py","line":147,"quote":"    \"torch.serialization\": \"load\",  # pickle could be used to load a different file"},{"file":"src/picklescan/scanner.py","line":161,"quote":"# TODO: handle methods loading other Pickle files (either mark as suspicious, or follow calls to scan other files [preventing infinite loops])"},{"file":"src/picklescan/scanner.py","line":171,"quote":"# torch.load()"},{"file":"src/picklescan/scanner.py","line":317,"quote":"        unsafe_filter = _unsafe_globals.get(g.module)"},{"file":"src/picklescan/scanner.py","line":322,"quote":"        elif unsafe_filter is not None and (unsafe_filter == \"*\" or g.name in unsafe_filter):"},{"file":"src/picklescan/scanner.py","line":325,"quote":"            issues_count += 1"},{"file":"src/picklescan/scanner.py","line":329,"quote":"            g.safety = SafetyLevel.Suspicious"}]}
```

## Fix

Add an exact `torch.load` entry to the unsafe-global table. Using a set containing only `load` makes the existing membership check flag that name without changing how other `torch` globals are classified.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -140,6 +140,7 @@
     "pip": "*",
     "pydoc": "pipepager",  # pydoc.pipepager('help','echo pwned')
     "timeit": "*",
+    "torch": {"load"},
     "torch._dynamo.guards": {"GuardBuilder.get"},
     "torch._inductor.codecache": "compile_file",  # compile_file('', '', ['sh', '-c','$(echo pwned)'])
     "torch.fx.experimental.symbolic_shapes": {"ShapeEnv.evaluate_guards_expression"},
```

## Self-assessment

```json
{"claim":1,"confidence":0.86}
```
