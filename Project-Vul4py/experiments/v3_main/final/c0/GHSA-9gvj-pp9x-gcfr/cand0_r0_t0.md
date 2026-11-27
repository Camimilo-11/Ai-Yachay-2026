## Vulnerability

**CWE-248: Uncaught Exception** in `src/picklescan/scanner.py`, in `_list_globals`’s handling of `STACK_GLOBAL`. The backward search excludes opcode index 0, the memo lookup assumes the referenced entry exists, and memoized operands are passed to the classifier without checking that they are strings. An attacker can supply a pickle that triggers one of these unchecked cases and aborts the scan before it reports any findings. `scan_pickle_bytes` catches `GenOpsError`, not these exceptions.

```json
{"evidence":[{"file":"src/picklescan/scanner.py","line":234,"quote":"            for op in pickletools.genops(data):"},{"file":"src/picklescan/scanner.py","line":248,"quote":"                memo[len(memo)] = ops[n - 1][1]"},{"file":"src/picklescan/scanner.py","line":255,"quote":"                for offset in range(1, n):"},{"file":"src/picklescan/scanner.py","line":264,"quote":"                        values.append(memo[int(ops[n - offset][1])])"},{"file":"src/picklescan/scanner.py","line":280,"quote":"                    raise ValueError("},{"file":"src/picklescan/scanner.py","line":283,"quote":"                globals.add((values[1], values[0]))"},{"file":"src/picklescan/scanner.py","line":310,"quote":"        if \"unknown\" in g.module or \"unknown\" in g.name:"},{"file":"src/picklescan/scanner.py","line":311,"quote":"            g.safety = SafetyLevel.Dangerous"},{"file":"src/picklescan/scanner.py","line":338,"quote":"    except GenOpsError as e:"}]}
```

## Fix

Include opcode index 0 in the search. Treat missing or non-string memo values and incomplete operand pairs as `unknown`, so the existing classifier reports them as dangerous rather than aborting the scan. Imports whose operands resolve to two strings keep their existing classification.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -252,16 +252,17 @@
                 globals.add(tuple(op_value.split(" ", 1)))
             elif op_name == "STACK_GLOBAL":
                 values = []
-                for offset in range(1, n):
+                for offset in range(1, n + 1):
                     if ops[n - offset][0].name in [
                         "MEMOIZE",
                         "PUT",
                         "BINPUT",
                         "LONG_BINPUT",
                     ]:
                         continue
                     if ops[n - offset][0].name in ["GET", "BINGET", "LONG_BINGET"]:
-                        values.append(memo[int(ops[n - offset][1])])
+                        value = memo.get(int(ops[n - offset][1]))
+                        values.append(value if isinstance(value, str) else "unknown")
                     elif ops[n - offset][0].name not in [
                         "SHORT_BINUNICODE",
                         "UNICODE",
@@ -277,10 +278,9 @@
                     if len(values) == 2:
                         break
                 if len(values) != 2:
-                    raise ValueError(
-                        f"Found {len(values)} values for STACK_GLOBAL at position {n} instead of 2."
-                    )
-                globals.add((values[1], values[0]))
+                    globals.add(("unknown", "unknown"))
+                else:
+                    globals.add((values[1], values[0]))
 
         if not multiple_pickles:
             break
```

## Self-assessment

```json
{"claim":1,"confidence":0.88}
```
