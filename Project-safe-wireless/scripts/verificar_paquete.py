"""Comprueba los archivos distribuidos; no requiere paquetes externos."""
import hashlib
import json
from pathlib import Path, PurePosixPath


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
    errors = []
    for entry in manifest["files"]:
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in entry["path"]:
            raise ValueError("Ruta no valida en el manifiesto")
        path = root.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Ruta fuera del paquete")
        if not path.is_file():
            errors.append(f"Falta: {relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            errors.append(f"Cambio: {relative}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Integridad correcta: {len(manifest['files'])} archivos verificados.")
    print("Los archivos nuevos de tus ejecuciones no forman parte del manifiesto.")


if __name__ == "__main__":
    main()
