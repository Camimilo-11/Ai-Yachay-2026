## Vulnerability

**Scanner bypass (CWE-693) in `src/picklescan/scanner.py`, `_list_globals`.** The scanner reconstructs `STACK_GLOBAL` operands by walking backward through attacker-controlled pickle opcodes. It resolves earlier memo reads against the memo as it exists at `STACK_GLOBAL`, not as it existed when each read occurred. A crafted pickle can overwrite a memo slot after reading it, causing the scanner to classify the replacement string instead of the operand already on the pickle stack. This can hide a dangerous import. The same code can abort the scan on a missing memo entry or an incomplete operand pair.

```json
{"evidence":[{"file":"src/picklescan/scanner.py","line":234,"quote":"            for op in pickletools.genops(data):"},{"file":"src/picklescan/scanner.py","line":250,"quote":"                memo[op_value] = ops[n - 1][1]"},{"file":"src/picklescan/scanner.py","line":251,"quote":"            elif op_name in (\"GLOBAL\", \"INST\"):"},{"file":"src/picklescan/scanner.py","line":255,"quote":"                for offset in range(1, n):"},{"file":"src/picklescan/scanner.py","line":264,"quote":"                        values.append(memo[int(ops[n - offset][1])])"},{"file":"src/picklescan/scanner.py","line":279,"quote":"                if len(values) != 2:"},{"file":"src/picklescan/scanner.py","line":280,"quote":"                    raise ValueError("},{"file":"src/picklescan/scanner.py","line":283,"quote":"                globals.add((values[1], values[0]))"},{"file":"src/picklescan/scanner.py","line":310,"quote":"        if \"unknown\" in g.module or \"unknown\" in g.name:"},{"file":"src/picklescan/scanner.py","line":317,"quote":"            unsafe_filter == \"*\" or g.name in unsafe_filter"},{"file":"src/picklescan/scanner.py","line":338,"quote":"    except GenOpsError as e:"}]}
```

## Fix

Resolve memo reads in opcode order and retain the resolved operands, so a later write cannot retroactively change the import being classified. Start tracking at the first opcode and use the existing dangerous `unknown` marker when an operand cannot be resolved. Direct `GLOBAL` and `INST` handling and the supported Unicode operand opcodes remain unchanged.

## Patch

```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -238,49 +238,35 @@
         last_byte = data.read(1)
         data.seek(-1, 1)
 
-        # Extract global imports
-        for n in range(len(ops)):
-            op = ops[n]
-            op_name = op[0].name
-            op_value = op[1]
+        # Resolve memo reads before later writes can change their values.
+        previous_value = value = "unknown"
+        for opcode, op_value, _ in ops:
+            op_name = opcode.name
 
-            if op_name == "MEMOIZE" and n > 0:
-                memo[len(memo)] = ops[n - 1][1]
-            elif op_name in ["PUT", "BINPUT", "LONG_BINPUT"] and n > 0:
-                memo[op_value] = ops[n - 1][1]
-            elif op_name in ("GLOBAL", "INST"):
+            if op_name == "MEMOIZE":
+                memo[len(memo)] = value
+                continue
+            if op_name in ("PUT", "BINPUT", "LONG_BINPUT"):
+                memo[op_value] = value
+                continue
+
+            if op_name in ("GLOBAL", "INST"):
                 globals.add(tuple(op_value.split(" ", 1)))
             elif op_name == "STACK_GLOBAL":
-                values = []
-                for offset in range(1, n):
-                    if ops[n - offset][0].name in [
-                        "MEMOIZE",
-                        "PUT",
-                        "BINPUT",
-                        "LONG_BINPUT",
-                    ]:
-                        continue
-                    if ops[n - offset][0].name in ["GET", "BINGET", "LONG_BINGET"]:
-                        values.append(memo[int(ops[n - offset][1])])
-                    elif ops[n - offset][0].name not in [
-                        "SHORT_BINUNICODE",
-                        "UNICODE",
-                        "BINUNICODE",
-                        "BINUNICODE8",
-                    ]:
-                        _log.debug(
-                            "Presence of non-string opcode, categorizing as an unknown dangerous import"
-                        )
-                        values.append("unknown")
-                    else:
-                        values.append(ops[n - offset][1])
-                    if len(values) == 2:
-                        break
-                if len(values) != 2:
-                    raise ValueError(
-                        f"Found {len(values)} values for STACK_GLOBAL at position {n} instead of 2."
-                    )
-                globals.add((values[1], values[0]))
+                globals.add((previous_value, value))
+
+            previous_value = value
+            if op_name in (
+                "SHORT_BINUNICODE",
+                "UNICODE",
+                "BINUNICODE",
+                "BINUNICODE8",
+            ):
+                value = op_value
+            elif op_name in ("GET", "BINGET", "LONG_BINGET"):
+                value = memo.get(int(op_value), "unknown")
+            else:
+                value = "unknown"
 
         if not multiple_pickles:
             break
```

## Self-assessment

```json
{"claim":1,"confidence":0.88}
```
