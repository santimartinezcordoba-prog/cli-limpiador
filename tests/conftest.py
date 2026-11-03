"""Fixtures y utilidades compartidas por todos los tests.

REGLA DE ORO: ningún test toca ficheros reales. Todo se crea dentro de
`tmp_path`, la carpeta temporal que pytest crea y destruye solo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from limpiador.cli import app, console

# Configuración de ejemplo con las 4 operaciones que usan los tests.
CONFIG_VALIDA: dict[str, Any] = {
    "version": 1,
    "acciones": [
        {
            "nombre": "mover-imagenes",
            "descripcion": "Mueve imágenes a una carpeta imagenes/",
            "operacion": "mover",
            "patrones": ["*.png", "*.jpg", "*.jpeg", "*.webp"],
            "destino": "imagenes",
        },
        {
            "nombre": "borrar-temporales",
            "descripcion": "Borra ficheros temporales .tmp",
            "operacion": "borrar",
            "patrones": ["*.tmp"],
        },
        {
            "nombre": "ordenar-documentos",
            "descripcion": "Mueve PDF y DOCX a documentos/",
            "operacion": "mover",
            "patrones": ["*.pdf", "*.docx"],
            "destino": "documentos",
        },
        {
            "nombre": "renombrar-viejos",
            "descripcion": "Añade el sufijo -revisar a los .txt",
            "operacion": "renombrar",
            "patrones": ["*.txt"],
            "sufijo": "revisar",
        },
    ],
}


@pytest.fixture(autouse=True)
def _salida_determinista(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consola de Rich ancha y sin códigos ANSI para que los tests sean estables.

    COLUMNS=200 evita que Rich parta las líneas y podemos buscar frases
    completas en la salida. `force_terminal=False` apaga los códigos ANSI de
    forma determinista: en algunos entornos (p. ej. GitHub Actions, donde una
    versión de Rich detectó mal la terminal y emitió escapes) palabras como
    `--config` quedaban divididas en spans de estilo y rompían las
    comprobaciones por substring sobre la salida en crudo.
    """
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(console, "_force_terminal", False)
    monkeypatch.setattr(console, "_environ", {})
    monkeypatch.setattr(console, "_width", 200)


@pytest.fixture()
def runner() -> CliRunner:
    """Runner oficial de Typer para invocar la CLI sin lanzar procesos."""
    return CliRunner()


def llamar(
    runner: CliRunner,
    args: list[str],
    config: Path | None = None,
    entrada: str | None = None,
) -> Result:
    """Invoca `limpiador` añadiendo `--config` si se pasa una ruta concreta."""
    base = ["--config", str(config)] if config is not None else []
    return runner.invoke(app, [*base, *args], input=entrada)


def escribir_config(tmp_path: Path, contenido: object) -> Path:
    """Escribe una configuración (dict o texto crudo) y devuelve su ruta."""
    ruta = tmp_path / "acciones.json"
    if isinstance(contenido, str):
        ruta.write_text(contenido, encoding="utf-8")
    else:
        ruta.write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
    return ruta


@pytest.fixture()
def config_valida(tmp_path: Path) -> Path:
    """Fichero `acciones.json` válido dentro de la carpeta temporal."""
    return escribir_config(tmp_path, CONFIG_VALIDA)


@pytest.fixture()
def carpeta_pruebas(tmp_path: Path) -> Path:
    """Carpeta con ficheros de todo tipo para ejecutar acciones.

    Incluye una subcarpeta con un PDF para comprobar que las acciones
    NO son recursivas (solo actúan sobre el primer nivel).
    """
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    for nombre in (
        "foto.png",
        "selfie.jpg",
        "informe.pdf",
        "nota.docx",
        "datos.tmp",
        "readme.txt",
    ):
        (carpeta / nombre).write_bytes(f"contenido de {nombre}".encode())
    sub = carpeta / "sub"
    sub.mkdir()
    (sub / "notas.pdf").write_bytes(b"pdf en subcarpeta")
    return carpeta


def instantanea(raiz: Path) -> dict[str, str]:
    """Fotografía el estado de una carpeta: ruta relativa -> contenido.

    Los tests comparan la instantánea antes y después para demostrar que
    `--simular` (y las cancelaciones) no modifican absolutamente nada.
    """
    estado: dict[str, str] = {}
    for ruta in sorted(raiz.rglob("*")):
        clave = str(ruta.relative_to(raiz))
        if ruta.is_symlink():
            estado[clave] = "<enlace simbólico>"
        elif ruta.is_dir():
            estado[clave] = "<carpeta>"
        else:
            estado[clave] = ruta.read_bytes().hex()
    return estado
