## Vulnerability
**CWE-754: Improper Check for Unusual or Exceptional Conditions** in `_list_globals`. The scanner infers `STACK_GLOBAL` operands by walking backward through the opcode list and looking up entries in a memo populated from adjacent opcode arguments. Those arguments are not necessarily the values on the pickle stack. A crafted pickle can therefore make the scanner report the wrong global or raise an exception when a memo entry or operand is missing. The latter can interrupt scanning instead of returning findings because `scan_pickle_bytes` catches `GenOpsError`, not those lookup or operand errors.

```json
{"evidence":[{"file":"src/picklescan/scanner.py","line":234,"quote":"            for op in pickletools.genops(data):"},{"file":"src/picklescan/scanner.py","line":248,"quote":"                memo[len(memo)] = ops[n - 1][1]"},{"file":"src/picklescan/scanner.py","line":252,"quote":"                globals.add(tuple(op_value.split(\" \", 1)))"},{"file":"src/picklescan/scanner.py","line":255,"quote":"                for offset in range(1, n):"},{"file":"src/picklescan/scanner.py","line":264,"quote":"                        values.append(memo[int(ops[n - offset][1])])"},{"file":"src/picklescan/scanner.py","line":280,"quote":"                    raise ValueError("},{"file":"src/picklescan/scanner.py","line":283,"quote":"                globals.add((values[1], values[0]))"},{"file":"src/picklescan/scanner.py","line":310,"quote":"        if \"unknown\" in g.module or \"unknown\" in g.name:"},{"file":"src/picklescan/scanner.py","line":311,"quote":"            g.safety = SafetyLevel.Dangerous"},{"file":"src/picklescan/scanner.py","line":338,"quote":"    except GenOpsError as e:"}]}
```

## Fix
Track the top two operands in opcode order and record memo values when they are stored. If a memo value is missing or an opcode makes the operands uncertain, use the existing `unknown` classification so the scanner reports a dangerous reference rather than guessing or aborting. Direct `GLOBAL` and `INST` extraction and the existing parse-error handling remain unchanged.

## Patch
```diff
--- a/src/picklescan/scanner.py
+++ b/src/picklescan/scanner.py
@@ -238,50 +238,33 @@
         last_byte = data.read(1)
         data.seek(-1, 1)
 
-        # Extract global imports
-        for n in range(len(ops)):
-            op = ops[n]
-            op_name = op[0].name
-            op_value = op[1]
-
-            if op_name == "MEMOIZE" and n > 0:
-                memo[len(memo)] = ops[n - 1][1]
-            elif op_name in ["PUT", "BINPUT", "LONG_BINPUT"] and n > 0:
-                memo[op_value] = ops[n - 1][1]
+        # Track the top two values used by STACK_GLOBAL without guessing the
+        # effects of unhandled opcodes.
+        previous = top = "unknown"
+        for opcode, op_value, _ in ops:
+            op_name = opcode.name
+            if op_name == "MEMOIZE":
+                memo[len(memo)] = top
+            elif op_name in ("PUT", "BINPUT", "LONG_BINPUT"):
+                memo[op_value] = top
+            elif op_name in ("GET", "BINGET", "LONG_BINGET"):
+                previous, top = top, memo.get(op_value, "unknown")
+            elif op_name in (
+                "SHORT_BINUNICODE",
+                "UNICODE",
+                "BINUNICODE",
+                "BINUNICODE8",
+            ):
+                previous, top = top, op_value
             elif op_name in ("GLOBAL", "INST"):
                 globals.add(tuple(op_value.split(" ", 1)))
+                previous = top = "unknown"
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
+                globals.add((previous, top))
+                previous = top = "unknown"
+            elif op_name not in ("PROTO", "FRAME"):
+                previous = top = "unknown"
 
         if not multiple_pickles:
             break
 
```

## Self-assessment
```json
{"claim":1,"confidence":0.89}
```
