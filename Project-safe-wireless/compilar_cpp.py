"""Compila el EM C++17 con g++ y registra compilador, flags y fuentes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
EXE = BUILD / ("em.exe" if os.name == "nt" else "em")
MANIFEST = BUILD / "em_build.json"
FLAGS = ["-std=c++17", "-O2", "-Wall", "-Wextra", "-pedantic", "-static"]


def build_em() -> Path:
    """Recompila si falta el ejecutable o cambió la fuente/configuración."""
    source_hash = hashlib.sha256((ROOT / "em.cpp").read_bytes()).hexdigest()
    if EXE.exists() and MANIFEST.exists():
        metadata = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if metadata.get("source_sha256") == source_hash and metadata.get("flags") == FLAGS:
            return EXE
    compiler = os.environ.get("CXX") or shutil.which("g++")
    if not compiler and Path(r"C:\msys64\mingw64\bin\g++.exe").exists():
        compiler = r"C:\msys64\mingw64\bin\g++.exe"
    if not compiler:
        raise FileNotFoundError("Instala g++ con C++17 o define CXX con la ruta al compilador.")
    BUILD.mkdir(exist_ok=True)
    command = [compiler, *FLAGS, str(ROOT / "em.cpp"), "-o", str(EXE)]
    subprocess.run(command, cwd=ROOT, check=True, timeout=120)
    version = subprocess.run([compiler, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    metadata = {"backend": "C++17", "source": "em.cpp", "source_sha256": source_hash,
                "compiler": str(compiler), "compiler_version": version, "flags": FLAGS,
                "command": command, "executable": str(EXE)}
    MANIFEST.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return EXE


if __name__ == "__main__":
    print(f"EM C++17 compilado: {build_em()}")
