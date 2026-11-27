## Review

### Candidate P1

P1 makes two unrelated changes:

1. It extends `"*"` denylist rules to dotted submodules in `_build_scan_result_from_raw_globals`.
2. It adds local-directory content sniffing for files with unsupported extensions.

The first change may catch some submodule bypasses, but the patch as a whole does **not** remove the vulnerability, because several major scanner entry points remain extension-gated and are untouched.

#### Remaining bypasses

- **Hugging Face scanning is still filtered by extension before any bytes are fetched.** In `scan_huggingface_model`, a model file is excluded unless its extension is in `_zip_file_extensions`, `_pickle_file_extensions`, or `_pytorch_file_extensions`:

  ```python
  file_ext = os.path.splitext(file_name)[1]
  if (
      file_ext not in _zip_file_extensions
      and file_ext not in _pickle_file_extensions
      and file_ext not in _pytorch_file_extensions
  ):
      continue
  ```

  P1 does not change this. A Hugging Face repository containing `model.weights` with a valid protocol-0 pickle such as

  ```text
  cposix
  system
  (S'id'
  tR.
  ```

  is skipped before it is downloaded or scanned. `picklescan -hf <repo>` then reports zero dangerous globals and exits `0`.

- **ZIP member scanning is still extension/magic-number gated.** `scan_zip_bytes` only scans a member if its extension is in `_pickle_file_extensions` or its first bytes look like a v2+ pickle header:

  ```python
  if file_ext in _pickle_file_extensions or any(
      magic_bytes.startswith(mn) for mn in _pickle_magic_bytes
  ):
  ```

  A protocol-0 pickle has no `\x80` header, so the same payload stored in a ZIP as `payload.txt` is silently skipped. This is reachable from local ZIP scanning and from `-u` if the URL points to a ZIP archive.

- **7z scanning is still extension-gated.** `scan_7z_bytes` extracts only targets ending in `_pickle_file_extensions`:

  ```python
  targets = [f for f in file_names if f.endswith(tuple(_pickle_file_extensions))]
  ```

  P1 does not change that path either.

Therefore the same renamed raw pickle is caught by P1 only when it is a loose file under a local directory passed to `-p`. The same payload is missed inside archives and in Hugging Face model repositories.

#### Functionality regression

P1’s `_has_pickle_globals` has a `while True` loop around `pickletools.genops(data)` with no normal `return False` exit. If `genops` successfully parses a pickle that contains no `GLOBAL`, `INST`, or `STACK_GLOBAL` opcode, the inner `for` loop finishes, the surrounding `while True` immediately starts another parse at EOF, and the function does not return. For example, a local unsupported-extension file containing the valid innnocuous pickle bytes `N.` would cause this loop rather than being skipped.

P1 also makes the directory scanner open every regular file with an unsupported extension. Files that cannot be read now raise an exception where they were previously skipped by the extension filter, aborting the whole directory scan through the CLI’s exception path.

So P1 neither removes the end-to-end vulnerability nor preserves the existing scanning behaviour.

## Verdict

```json
{
  "candidates": {
    "P1": {
      "removes_vulnerability": 0,
      "preserves_functionality": 0,
      "claim": 0,
      "confidence": 0.02,
      "evidence": [
        {
          "file": "src/picklescan/scanner.py",
          "line": 510,
          "quote": "            file_ext not in _zip_file_extensions"
        },
        {
          "file": "src/picklescan/scanner.py",
          "line": 511,
          "quote": "            and file_ext not in _pickle_file_extensions"
        },
        {
          "file": "src/picklescan/scanner.py",
          "line": 514,
          "quote": "            continue"
        },
        {
          "file": "src/picklescan/scanner.py",
          "line": 392,
          "quote": "                if file_ext in _pickle_file_extensions or any("
        },
        {
          "file": "src/picklescan/scanner.py",
          "line": 367,
          "quote": "        targets = [f for f in file_names if f.endswith(tuple(_pickle_file_extensions))]"
        },
        {
          "file": "src/picklescan/cli.py",
          "line": 85,
          "quote": "        return 0 if scan_result.issues_count == 0 else 1"
        }
      ],
      "counterexample": "A Hugging Face repo with file 'model.weights' containing protocol-0 pickle cposix\\nsystem\\n(S'id'\\ntR. is skipped by extension before download, so picklescan -hf repo returns 0 issues and exits 0. The same payload inside a ZIP as 'payload.txt' is also skipped because .txt is not a pickle extension and protocol 0 has no \\x80 header."
    }
  },
  "best": "none"
}
```
