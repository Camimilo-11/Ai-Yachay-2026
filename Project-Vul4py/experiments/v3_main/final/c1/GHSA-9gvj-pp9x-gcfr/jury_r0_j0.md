## Review

**P1**

*What the vulnerability is.* The original `STACK_GLOBAL` handling guesses its two operands by walking backward from the opcode. The walk stops before reaching `ops[0]`:

- The loop bound is `for offset in range(1, n):` (line 255), so `offset` never reaches `n`.
- Take a pickle with no `PROTO` opcode: `SHORT_BINUNICODE 'os'`, `SHORT_BINUNICODE 'system'`, `STACK_GLOBAL`, ….
  - At `n=2` only one value is collected.
  - That raises `ValueError` (line 280).
  - `scan_pickle_bytes` only catches `GenOpsError` (line 338), so the `ValueError` escapes.
  - The scan aborts and the dangerous import is never reported.
- A `BINGET` with no matching memo entry crashes the same way. It raises `KeyError` at `values.append(memo[int(ops[n - offset][1])])` (line 264).

*Does P1 remove it?* Yes, for the reachable cases I could find.

- **Every opcode is visited.** P1 iterates all ops with `for opcode, op_value, _ in ops:`, including `ops[0]`. The PROTO-less `os system` pickle now yields `('os','system')`. That pair matches `"os": "*"` and is reported as Dangerous.
- **Missing memo entries no longer crash.** They become `"unknown"` via `memo.get(op_value, "unknown")`. That value hits the existing `if "unknown" in g.module or "unknown" in g.name:` branch (line 310) and is marked Dangerous.
- **The `ValueError` is gone.** P1 removes the raise, so neither crash path remains.

*Can an attacker make P1 misreport?* I checked whether P1's top-two stack model can be made to show a safe global while the real stack holds a dangerous one. I found no in-pickle way.

- Only four groups of opcodes are modelled:
  - `PUT`/`MEMOIZE` store the current top and leave the stack unchanged.
  - `GET` pushes the stored memo value.
  - Unicode string opcodes push their value.
  - `PROTO`/`FRAME` are skipped.
- These match real unpickler semantics.
- Every other opcode resets both slots to `"unknown"`. That covers `STRING`/`BINSTRING`, `POP`, `DUP`, `MARK` and others. The failure mode is therefore a Dangerous false positive, never a false negative.
- Memo values are now recorded from the tracked stack top rather than from the adjacent opcode's argument. This closes the "PUT after an unrelated opcode" guessing that the original code did.

*Residual weakness (not introduced by P1).* `memo = {}` is created once per `_list_globals` call. It persists across the multiple pickles in one file, whereas a real unpickler starts each load with an empty memo. Because `MEMOIZE` keys are computed as `len(memo)`, indices drift from the real ones after a first pickle.

- A two-pickle file could exploit this. The second pickle would `BINGET` an index that the first pickle filled with safe strings.
- This affects the original code identically and lies outside the hinted lines.
- It only matters if a victim loads several pickles from one stream.
- It lowers my confidence somewhat, but it does not count against P1 relative to the baseline.

*Does P1 preserve functionality?* Yes.

- **Legitimate protocol 4/5 pickles.** These contain `FRAME`, `SHORT_BINUNICODE mod`, `MEMOIZE`, `SHORT_BINUNICODE name`, `MEMOIZE`, `STACK_GLOBAL`, or reuse strings via `BINGET`. All of these are tracked exactly, so safe globals such as `collections OrderedDict` stay Innocuous.
- **`GLOBAL`/`INST` extraction is unchanged.** `globals.add(tuple(op_value.split(" ", 1)))` (line 252) is kept. Protocol 2/3 torch and numpy pickles behave as before.
- **Memo keys still match.** `PUT`/`GET` arguments from `pickletools` are ints, so memo keys line up as they did with the original `int(...)`.
- **Error handling is unchanged.** `GenOpsError` handling, the `multiple_pickles` behaviour and all public names are untouched.

## Verdict
```json
{"candidates": {"P1": {"removes_vulnerability": 1, "preserves_functionality": 1, "claim": 1, "confidence": 0.75, "evidence": [{"file": "src/picklescan/scanner.py", "line": 255, "quote": "for offset in range(1, n):"}, {"file": "src/picklescan/scanner.py", "line": 264, "quote": "values.append(memo[int(ops[n - offset][1])])"}, {"file": "src/picklescan/scanner.py", "line": 280, "quote": "raise ValueError("}, {"file": "src/picklescan/scanner.py", "line": 338, "quote": "except GenOpsError as e:"}, {"file": "src/picklescan/scanner.py", "line": 310, "quote": "if \"unknown\" in g.module or \"unknown\" in g.name:"}, {"file": "src/picklescan/scanner.py", "line": 252, "quote": "globals.add(tuple(op_value.split(\" \", 1)))"}], "counterexample": ""}}, "best": "P1"}
```
