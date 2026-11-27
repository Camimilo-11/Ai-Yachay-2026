## Overview

The command-line interface accepts a path, a URL, or a Hugging Face model name and passes the selected input to a scanner entry point. [E1][E2] The scanner parses pickle data and classifies discovered globals as innocuous, suspicious, or dangerous. [E3][E4] It also provides scanning paths for archives and NumPy/PyTorch-related inputs. [E5][E6] Scan results carry file, issue, infection, and error counts, and can be merged. [E7]

## Components

### `src/picklescan/cli.py`

Purpose: parses command-line arguments, invokes the selected scanner, and reports a summary. [E1][E2]

- `print_summary(show_globals: bool, sr: ScanResult)` — logs scan counts and, when requested, the globals found. [E8]
- `main()` — configures logging and argument parsing, selects a scan target, prints the result, and returns a status code. [E2][E9]

### `src/picklescan/scanner.py`

Purpose: defines scan result types and scanning routines for pickle data and supported file or remote inputs. [E3][E7][E10]

- `SafetyLevel(Enum)` — defines the `Innocuous`, `Suspicious`, and `Dangerous` levels. [E3]
- `Global(module: str, name: str, safety: SafetyLevel)` — represents a discovered global and its safety classification. [E4]
- `ScanResult(globals: List[Global], scanned_files: int = 0, issues_count: int = 0, infected_files: int = 0, scan_err: bool = False)` — stores scan findings and summary counts. [E7]
- `ScanResult.merge(self, sr: "ScanResult")` — combines another result’s globals, counts, and error state into this result. [E11]
- `scan_pickle_bytes(data: IO[bytes], file_id, multiple_pickles=True) -> ScanResult` — disassembles pickle data and builds a result from the globals it finds. [E12]
- `scan_bytes(data: IO[bytes], file_id, file_ext: Optional[str] = None) -> ScanResult` — dispatches a byte stream to a scanner based on its extension or detected format. [E13]
- `scan_directory_path(path) -> ScanResult` — walks a directory and merges results for files with supported extensions. [E14]
- `scan_file_path(path) -> ScanResult` — opens one path and scans its contents. [E15]
- `scan_url(url) -> ScanResult` — retrieves a URL’s bytes and scans them. [E16]
- `scan_huggingface_model(repo_id)` — obtains a model’s file listing and scans selected model files. [E17]

## Data flow and inputs

The CLI accepts mutually exclusive path, URL, and Hugging Face model arguments. [E1] For a path, it resolves an absolute path, checks that it exists, and chooses the directory or file scanner; for a URL or model name, it calls the corresponding scanner. [E2] Directory scanning walks the tree and filters files by extension before opening them as binary input. [E14] File scanning opens a path in binary mode, while URL scanning wraps retrieved bytes in an in-memory byte stream. [E15][E16] The byte-stream dispatcher selects PyTorch or NumPy handling for matching extensions; otherwise, it checks for ZIP and 7z formats before treating the data as pickle input. [E13][E18] The Hugging Face scanner requests model metadata, selects files with supported extensions, retrieves each selected file, and passes its bytes to the dispatcher. [E17][E19]

## Behaviour to preserve

The CLI’s `-p`/`--path`, `-u`/`--url`, and `-hf`/`--huggingface` options are mutually exclusive. [E1] It returns `2` when the result has a scan error, otherwise returns `0` when `issues_count` is zero and `1` when it is nonzero; an unhandled exception is logged and returns `2`. [E9] `ScanResult.merge` extends the globals list, adds the numeric counts, and combines `scan_err` with logical OR. [E11] The scanner distinguishes the three safety levels and builds the issue and infected-file counts from dangerous globals. [E3][E4][E20]

## Evidence

```json
[
  {
    "claim": "The CLI defines mutually exclusive path, URL, and Hugging Face model options.",
    "file": "src/picklescan/cli.py",
    "line": 33,
    "quote": "group = parser.add_mutually_exclusive_group()"
  },
  {
    "claim": "The CLI routes path, URL, and Hugging Face model inputs to corresponding scanner functions.",
    "file": "src/picklescan/cli.py",
    "line": 64,
    "quote": "if args.path is not None:"
  },
  {
    "claim": "The scanner defines innocuous, suspicious, and dangerous safety levels.",
    "file": "src/picklescan/scanner.py",
    "line": 24,
    "quote": "class SafetyLevel(Enum):"
  },
  {
    "claim": "A Global stores module, name, and safety fields.",
    "file": "src/picklescan/scanner.py",
    "line": 31,
    "quote": "class Global:"
  },
  {
    "claim": "ScanResult stores globals and scan summary fields.",
    "file": "src/picklescan/scanner.py",
    "line": 37,
    "quote": "class ScanResult:"
  },
  {
    "claim": "ScanResult.merge extends globals and adds result counts.",
    "file": "src/picklescan/scanner.py",
    "line": 44,
    "quote": "def merge(self, sr: \"ScanResult\"):"
  },
  {
    "claim": "The CLI summary logs scanned files, infected files, and dangerous globals.",
    "file": "src/picklescan/cli.py",
    "line": 13,
    "quote": "def print_summary(show_globals: bool, sr: ScanResult):"
  },
  {
    "claim": "The CLI main function configures and runs command-line processing.",
    "file": "src/picklescan/cli.py",
    "line": 26,
    "quote": "def main():"
  },
  {
    "claim": "The CLI returns status codes based on scan errors and issue counts, and catches unhandled exceptions.",
    "file": "src/picklescan/cli.py",
    "line": 82,
    "quote": "if scan_result.scan_err:"
  },
  {
    "claim": "Pickle scanning parses data and returns a ScanResult.",
    "file": "src/picklescan/scanner.py",
    "line": 344,
    "quote": "def scan_pickle_bytes(data: IO[bytes], file_id, multiple_pickles=True) -> ScanResult:"
  },
  {
    "claim": "The byte-stream scanner accepts an optional file extension.",
    "file": "src/picklescan/scanner.py",
    "line": 466,
    "quote": "def scan_bytes(data: IO[bytes], file_id, file_ext: Optional[str] = None) -> ScanResult:"
  },
  {
    "claim": "Directory scanning is exposed as a function taking a path.",
    "file": "src/picklescan/scanner.py",
    "line": 518,
    "quote": "def scan_directory_path(path) -> ScanResult:"
  },
  {
    "claim": "File scanning is exposed as a function taking a path.",
    "file": "src/picklescan/scanner.py",
    "line": 537,
    "quote": "def scan_file_path(path) -> ScanResult:"
  },
  {
    "claim": "URL scanning is exposed as a function taking a URL.",
    "file": "src/picklescan/scanner.py",
    "line": 543,
    "quote": "def scan_url(url) -> ScanResult:"
  },
  {
    "claim": "The Hugging Face scanner takes a repository ID.",
    "file": "src/picklescan/scanner.py",
    "line": 494,
    "quote": "def scan_huggingface_model(repo_id):"
  },
  {
    "claim": "Directory scanning walks paths and examines file names.",
    "file": "src/picklescan/scanner.py",
    "line": 520,
    "quote": "for base_path, _, file_names in os.walk(path):"
  },
  {
    "claim": "File scanning opens input in binary mode.",
    "file": "src/picklescan/scanner.py",
    "line": 539,
    "quote": "with open(path, \"rb\") as file:"
  },
  {
    "claim": "URL scanning wraps fetched bytes in BytesIO before scanning.",
    "file": "src/picklescan/scanner.py",
    "line": 544,
    "quote": "return scan_bytes(io.BytesIO(_http_get(url)), url)"
  },
  {
    "claim": "The Hugging Face scanner obtains model metadata through an HTTP request.",
    "file": "src/picklescan/scanner.py",
    "line": 496,
    "quote": "_http_get(f\"https://huggingface.co/api/models/{repo_id}\").decode(\"utf-8\")"
  },
  {
    "claim": "Dangerous globals contribute to issue counts, and a nonzero issue count contributes one infected file.",
    "file": "src/picklescan/scanner.py",
    "line": 325,
    "quote": "return ScanResult(globals, 1, issues_count, 1 if issues_count > 0 else 0, scan_err)"
  }
]
```
