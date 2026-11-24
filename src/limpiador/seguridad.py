"""Límites de trabajo y comprobantes de simulación de un solo uso."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from limpiador.config import Accion


def raiz_permitida() -> Path:
    """Carpeta de prácticas de la persona que ejecuta la CLI."""
    return (Path.home() / "pruebas-tareas").resolve()


def comprobar_limite(carpeta: Path) -> None:
    """Resuelve enlaces y rechaza carpetas fuera de la zona de prácticas."""
    if not carpeta.resolve().is_relative_to(raiz_permitida()):
        raise ValueError("La carpeta debe estar dentro de ~/pruebas-tareas.")


def _comprobante(accion: Accion, carpeta: Path) -> Path:
    identificador = hashlib.sha256(
        (str(carpeta.resolve()) + "\0" + accion.nombre).encode()
    ).hexdigest()
    return Path.home() / ".cache" / "limpiador" / "simulaciones" / identificador


def _huella(accion: Accion, carpeta: Path) -> str:
    """Incluye la configuración y los contenidos sin seguir enlaces simbólicos."""
    raiz = carpeta.resolve()
    huella = hashlib.sha256(accion.model_dump_json().encode())
    for ruta in sorted(raiz.rglob("*")):
        relativa = str(ruta.relative_to(raiz))
        huella.update(os.fsencode(relativa) + b"\0")
        if ruta.is_symlink():
            huella.update(b"L" + os.fsencode(os.readlink(ruta)) + b"\0")
        elif ruta.is_file():
            huella.update(b"F")
            with ruta.open("rb") as archivo:
                for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
                    huella.update(bloque)
            huella.update(b"\0")
        elif ruta.is_dir():
            huella.update(b"D\0")
        else:
            raise ValueError(f"Tipo de archivo no admitido: {relativa}")
    return huella.hexdigest()


def registrar_simulacion(accion: Accion, carpeta: Path) -> None:
    comprobante = _comprobante(accion, carpeta)
    huella = _huella(accion, carpeta)
    comprobante.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    comprobante.write_text(huella, encoding="ascii")


def consumir_simulacion(accion: Accion, carpeta: Path) -> bool:
    comprobante = _comprobante(accion, carpeta)
    try:
        anterior = comprobante.read_text(encoding="ascii")
    except FileNotFoundError:
        return False
    comprobante.unlink(missing_ok=True)
    return anterior == _huella(accion, carpeta)
