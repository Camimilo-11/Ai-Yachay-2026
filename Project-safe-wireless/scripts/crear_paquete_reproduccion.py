"""Crea un ZIP autónomo con código, dependencias, datos y documentación.

Ejecutar desde la raíz del proyecto: python scripts/crear_paquete_reproduccion.py
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "Project-safe-wireless-reproduccion.zip"
PACKAGE_DIR = "Project-safe-wireless"
PACKAGE_ITEMS = (
    ".gitignore",
    "README.md",
    "scripts",
    "config_integracion",
    "demo",
    "docs",
    "report",
    "results",
    "tools",
    "vendor",
    "requirements.txt",
    "requirements_docs.txt",
    "requirements_opcionales.txt",
)
OMIT_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".build", "build"}
OMIT_FILES = {
    "report/Propuesta_IA_RTI_EM.pdf",
    "report/Figura1.png",
    "report/Figura1.svg",
    "report/Figura1_flujo_metodologico.png",
    "report/Figura1_flujo_metodologico.svg",
    "report/Figura1_mapa_conceptual_bn.png",
    "report/Figura1_mapa_conceptual_bn.svg",
    "docs/Propuesta_IA_RTI_EM.md",
    "tools/render_proposal_pdf.py",
}
DOWNLOAD_LINE = "[Descarga el ZIP completo de reproducción](Project-safe-wireless-reproduccion.zip) y extrae la carpeta antes de ejecutar."
EXTRACTED_LINE = "La carpeta de reproducción ya está extraída; sigue los pasos siguientes."
PACKAGED_README_REPLACEMENTS = (
    ("[Resultados preliminares](resultados_preliminares/README.md) · gráficos, métricas y resúmenes.",
     "[Resultados preliminares](results/integracion_verificada/LEER_RESULTADOS.md) · gráficos, métricas y resúmenes."),
    ("[Ver resultados y trazabilidad](resultados_preliminares/README.md)",
     "[Ver resultados y trazabilidad](docs/TRACEABILIDAD_RESULTADOS.md)"),
)


def package_files() -> list[Path]:
    files = []
    for item in PACKAGE_ITEMS:
        source = ROOT / item
        if not source.exists():
            raise FileNotFoundError(f"Falta un elemento requerido del paquete: {item}")
        if source.is_file():
            candidates = [source]
        else:
            candidates = sorted(source.rglob("*"))
        for path in candidates:
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if relative.as_posix() in OMIT_FILES:
                continue
            if path.is_symlink() or any(part in OMIT_DIRS for part in relative.parts):
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(ROOT):
                raise ValueError(f"Ruta fuera del proyecto: {relative}")
            files.append(path)
    return sorted(set(files), key=lambda p: p.relative_to(ROOT).as_posix())


def write_manifest(staging: Path) -> None:
    files = sorted((p for p in staging.rglob("*") if p.is_file() and p.name != "SHA256SUMS.json"),
                   key=lambda p: p.relative_to(staging).as_posix())
    entries = []
    for path in files:
        data = path.read_bytes()
        entries.append({"path": path.relative_to(staging).as_posix(),
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    manifest = {"algorithm": "sha256", "file_count": len(entries), "files": entries}
    (staging / "SHA256SUMS.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    files = package_files()
    with tempfile.TemporaryDirectory(prefix="safe-wireless-package-") as temporary:
        staging = Path(temporary) / PACKAGE_DIR
        staging.mkdir()
        for source in files:
            relative = source.relative_to(ROOT)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        readme = staging / "README.md"
        content = readme.read_text(encoding="utf-8")
        if DOWNLOAD_LINE in content:
            content = content.replace(DOWNLOAD_LINE, EXTRACTED_LINE)
        elif EXTRACTED_LINE not in content:
            raise ValueError("No se encontró el enlace del ZIP esperado en README.md")
        for old, new in PACKAGED_README_REPLACEMENTS:
            if old in content:
                content = content.replace(old, new)
            elif new not in content:
                raise ValueError(f"No se encontró una ruta de resultados para el README del paquete: {old}")
        readme.write_text(content, encoding="utf-8")
        write_manifest(staging)

        temporary_archive = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".Project-safe-wireless-", suffix=".tmp",
                                             dir=ROOT, delete=False) as handle:
                temporary_archive = Path(handle.name)
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=9) as archive:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        name = PurePosixPath(PACKAGE_DIR, *path.relative_to(staging).parts).as_posix()
                        archive.write(path, name)
            with zipfile.ZipFile(temporary_archive) as archive:
                corrupt = archive.testzip()
                if corrupt:
                    raise zipfile.BadZipFile(f"Entrada dañada: {corrupt}")
            os.replace(temporary_archive, ARCHIVE)
            shutil.copy2(staging / "SHA256SUMS.json", ROOT / "SHA256SUMS.json")
            print(f"ZIP creado: {ARCHIVE}")
            print(f"Archivos incluidos (más SHA256SUMS.json): {len(files)}")
            print(f"Tamaño: {ARCHIVE.stat().st_size:,} bytes")
        finally:
            if temporary_archive and temporary_archive.exists():
                temporary_archive.unlink()


if __name__ == "__main__":
    main()
