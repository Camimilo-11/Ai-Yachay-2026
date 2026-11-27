## Overview
`scanner.py` provides functions for scanning pickle data and selected archive, NumPy, and PyTorch formats, returning `ScanResult` objects. [E1][E2][E3] It also provides entry points for scanning paths, URLs, and files listed by a Hugging Face model repository. [E4][E5][E6]

## Components
- **`src/picklescan/scanner.py`** — Defines the scan result and safety-level data model, parsing and format-specific scan functions, and path and network entry points. [E1][E2][E3][E4][E5][E6]
  - `SafetyLevel` — Enum of `Innocuous`, `Suspicious`, and `Dangerous` categories. [E1]
  - `Global(module: str, name: str, safety: SafetyLevel)` — Represents a global reference found in scanned data. [E7]
  - `ScanResult(globals: List[Global], scanned_files: int = 0, issues_count: int = 0, infected_files: int = 0, scan_err: bool = False)` — Holds scan findings and counters; `merge(self, sr: "ScanResult")` accumulates the other result’s globals, counters, and error flag. [E2][E8]
  - `_list_globals(data: IO[bytes], multiple_pickles=True) -> Set[Tuple[str, str]]` — Reads pickle opcodes and collects module/name pairs. [E3]
  - `scan_pickle_bytes(data: IO[bytes], file_id, multiple_pickles=True) -> ScanResult` — Scans pickle data and returns a result. [E9]
  - `scan_7z_bytes(data: IO[bytes], file_id) -> ScanResult` and `scan_zip_bytes(data: IO[bytes], file_id) -> ScanResult` — Scan supported archive contents. [E10][E11]
  - `scan_numpy(data: IO[bytes], file_id) -> ScanResult` and `scan_pytorch(data: IO[bytes], file_id) -> ScanResult` — Handle NumPy and PyTorch inputs. [E12][E13]
  - `scan_bytes(data: IO[bytes], file_id, file_ext: Optional[str] = None) -> ScanResult` — Selects a scanning route using the extension or detected format. [E14]
  - `scan_huggingface_model(repo_id)`, `scan_directory_path(path)`, `scan_file_path(path)`, and `scan_url(url)` — Entry points for repository, directory, file, and URL inputs. [E4][E5][E6]

## Data flow and inputs
- The byte-oriented functions accept a byte stream and, in several cases, a `file_id`; `scan_bytes` also accepts an optional extension. [E9][E12][E13][E14]
- Pickle parsing uses `pickletools.genops` to inspect opcodes, then collects global references for result construction. [E3][E15]
- `scan_bytes` routes PyTorch extensions to `scan_pytorch`, NumPy extensions to `scan_numpy`, and otherwise checks for ZIP and 7z formats before using the pickle scanner. [E14]
- ZIP scanning examines member names and content; it routes members to pickle scanning by extension or pickle magic bytes, and to NumPy scanning by extension or NumPy magic bytes. [E11][E16]
- `scan_directory_path` walks the supplied path and opens selected files in binary mode; `scan_file_path` opens its supplied path in binary mode. [E5][E6]
- `scan_url` downloads the supplied URL and wraps the response bytes in `io.BytesIO` before scanning. [E17][E18]
- `scan_huggingface_model` fetches model metadata, selects files by extension, downloads selected files, and passes their bytes to `scan_bytes`. [E4][E19][E20]

## Behaviour to preserve
- `ScanResult.merge` extends the globals list, adds the counters, and combines `scan_err` with a logical OR. [E8]
- The scanner’s result model exposes `globals`, `scanned_files`, `issues_count`, `infected_files`, and `scan_err`. [E2]
- The callable names and signatures listed above are the entry points and helper interfaces shown in this module. [E9][E10][E11][E12][E13][E14][E4][E5][E6]
- `scan_pickle_bytes` handles `GenOpsError` by logging the parsing error and returning a result with `scan_err=True`; when the exception contains globals, it builds the result from those globals. [E21]

## Evidence
```json
[
  {
    "claim": "The module defines three named safety levels.",
    "file": "src/picklescan/scanner.py",
    "line": 24,
    "quote": "class SafetyLevel(Enum):"
  },
  {
    "claim": "The scan result dataclass has a globals field and counters for scanned files, issues, infected files, and scan errors.",
    "file": "src/picklescan/scanner.py",
    "line": 36,
    "quote": "class ScanResult:"
  },
  {
    "claim": "The scanner iterates over pickle opcodes using pickletools.genops.",
    "file": "src/picklescan/scanner.py",
    "line": 228,
    "quote": "for op in pickletools.genops(data):"
  },
  {
    "claim": "The module provides a pickle-byte scanning function with a stream, file identifier, and multiple-pickle option.",
    "file": "src/picklescan/scanner.py",
    "line": 307,
    "quote": "def scan_pickle_bytes(data: IO[bytes], file_id, multiple_pickles=True) -> ScanResult:"
  },
  {
    "claim": "The module provides a function for scanning 7z archive bytes.",
    "file": "src/picklescan/scanner.py",
    "line": 325,
    "quote": "def scan_7z_bytes(data: IO[bytes], file_id) -> ScanResult:"
  },
  {
    "claim": "The module provides a function for scanning ZIP archive bytes.",
    "file": "src/picklescan/scanner.py",
    "line": 347,
    "quote": "def scan_zip_bytes(data: IO[bytes], file_id) -> ScanResult:"
  },
  {
    "claim": "The module provides a function for scanning NumPy data.",
    "file": "src/picklescan/scanner.py",
    "line": 377,
    "quote": "def scan_numpy(data: IO[bytes], file_id) -> ScanResult:"
  },
  {
    "claim": "The module provides a function for scanning PyTorch data.",
    "file": "src/picklescan/scanner.py",
    "line": 403,
    "quote": "def scan_pytorch(data: IO[bytes], file_id) -> ScanResult:"
  },
  {
    "claim": "The byte-scanning entry point accepts an optional file extension.",
    "file": "src/picklescan/scanner.py",
    "line": 430,
    "quote": "def scan_bytes(data: IO[bytes], file_id, file_ext: Optional[str] = None) -> ScanResult:"
  },
  {
    "claim": "The module provides a Hugging Face model scanning entry point.",
    "file": "src/picklescan/scanner.py",
    "line": 449,
    "quote": "def scan_huggingface_model(repo_id):"
  },
  {
    "claim": "The module provides a directory scanning entry point.",
    "file": "src/picklescan/scanner.py",
    "line": 474,
    "quote": "def scan_directory_path(path) -> ScanResult:"
  },
  {
    "claim": "The module provides a file-path scanning entry point.",
    "file": "src/picklescan/scanner.py",
    "line": 490,
    "quote": "def scan_file_path(path) -> ScanResult:"
  },
  {
    "claim": "The module provides a URL scanning entry point.",
    "file": "src/picklescan/scanner.py",
    "line": 495,
    "quote": "def scan_url(url) -> ScanResult:"
  },
  {
    "claim": "The result-merging method extends globals, adds the counters, and combines scan_err using logical OR.",
    "file": "src/picklescan/scanner.py",
    "line": 44,
    "quote": "self.globals.extend(sr.globals)"
  },
  {
    "claim": "The URL helper creates an HTTPS connection using the parsed URL's network location.",
    "file": "src/picklescan/scanner.py",
    "line": 202,
    "quote": "conn = http.client.HTTPSConnection(parsed_url.netloc)"
  },
  {
    "claim": "The URL entry point wraps downloaded bytes in an in-memory byte stream before scanning.",
    "file": "src/picklescan/scanner.py",
    "line": 496,
    "quote": "return scan_bytes(io.BytesIO(_http_get(url)), url)"
  },
  {
    "claim": "Directory scanning walks the supplied path.",
    "file": "src/picklescan/scanner.py",
    "line": 477,
    "quote": "for base_path, _, file_names in os.walk(path):"
  },
  {
    "claim": "The pickle-byte scanner handles GenOpsError by logging the parsing error.",
    "file": "src/picklescan/scanner.py",
    "line": 313,
    "quote": "_log.error(f\"ERROR: parsing pickle in {file_id}: {e}\")"
  },
  {
    "claim": "The pickle-byte scanner returns a scan-error result when the parsing exception has no globals.",
    "file": "src/picklescan/scanner.py",
    "line": 318,
    "quote": "return ScanResult([], scan_err=True)"
  }
]
```
