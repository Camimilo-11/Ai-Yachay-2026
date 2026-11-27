## Vulnerability

**Result: not found.** I could not establish an exploitable vulnerability in the shown code, so I am not proposing a patch.

**Where I looked:** The localization hint points to lines 255 and 269, which sit in the `STACK_GLOBAL` operand-recovery block of `_list_globals`. Line 255 is the unbounded backward scan (`range(1, n)`), and line 269 is the list of string opcodes.

**Why these lines do not show a bypass:**
- Every non-skipped opcode the backward scan meets is recorded as a value. Non-string opcodes are recorded as `"unknown"` (line 274), which the scanner treats as dangerous. This means a mismatch between the scanner's model and the real stack tends to raise an alarm rather than hide a global.
- Adding or missing entries in the string-opcode list (line 269) changes whether an operand is treated as a string or as `"unknown"`. Because `"unknown"` is flagged, a missing entry over-reports rather than under-reports.
- I traced how memo entries are recorded (`PUT`/`MEMOIZE` store the previous op's argument) and could not construct a case where the scanner records a benign string while the real unpickler holds a different string on the stack.

**Robustness issues I observed, which I do not classify as this vulnerability:**
- Line 264 (`memo[int(...)]`) can raise `KeyError`. Line 280 raises `ValueError` when fewer than two operands are found. Line 283 can store `None` or `int` values in the globals, which later cause a `TypeError`. These exceptions are not caught by `scan_pickle_bytes`, which only handles `GenOpsError`. The result is a loud crash of the scan, not a silent pass. I did not verify the downstream exception handling in every caller.

I cannot prove that the hinted lines contain the vulnerability from the shown code. Under the no-guess rule, I am reporting this as not found.

```json
{"evidence": [{"file": "src/picklescan/scanner.py", "line": 255, "quote": "for offset in range(1, n):"}, {"file": "src/picklescan/scanner.py", "line": 264, "quote": "values.append(memo[int(ops[n - offset][1])])"}, {"file": "src/picklescan/scanner.py", "line": 269, "quote": "\"BINUNICODE8\","}, {"file": "src/picklescan/scanner.py", "line": 274, "quote": "values.append(\"unknown\")"}, {"file": "src/picklescan/scanner.py", "line": 283, "quote": "globals.add((values[1], values[0]))"}]}
```

## Fix

No patch is proposed. Any change I made to lines 255 or 269 would be a guess. The conservative behaviour of the `"unknown"` fallback suggests those lines do not contain a silent bypass. If the maintainers have a specific exploit for this block, a concrete pickle sample that the scanner passes while the real unpickler executes a dangerous global would let me locate the faulty logic and propose a targeted fix.

## Patch

No patch. The empty block below is intentional.

```diff
```

## Self-assessment

```json
{"claim": 0, "confidence": 0.05}
```
