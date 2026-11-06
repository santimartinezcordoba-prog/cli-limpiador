"""Prueba estrella de seguridad: `--simular` NO toca el disco.

Demostración empírica con `tree_hash` (conftest): se fotografía el árbol
completo (rutas + contenidos) ANTES y DESPUÉS de simular y se exige que el
SHA256 sea IDÉNTICO. Si una sola implementación escribiera, renombrara o
creara una carpeta aunque fuera vacía, el hash cambiaría y el test estalla.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import llamar, salida_normalizada, tree_hash

# Acciones de CONFIG_VALIDA parametrizadas por operacion.
ACCIONES_A_SIMULAR = ("mover-imagenes", "borrar-temporales", "renombrar-viejos")


@pytest.fixture()
def mix_de_ficheros(tmp_path: Path) -> Path:
    """Carpeta con tipos variados: png, jpg, pdf, tmp (+ txt y subcarpeta)."""
    carpeta = tmp_path / "mezcla"
    carpeta.mkdir()
    contenidos = {
        "foto.png": b"\x89PNG datos de imagen fake",
        "selfie.jpg": b"\xff\xd8\xff datos jpeg fake",
        "informe.pdf": b"%PDF-1.4 informe",
        "cache.tmp": b"basura temporal",
        "readme.txt": b"un readme cualquiera",
    }
    for nombre, bytes_ in contenidos.items():
        (carpeta / nombre).write_bytes(bytes_)
    sub = carpeta / "sub"
    sub.mkdir()
    (sub / "anidado.png").write_bytes(b"\x89PNG anidado")
    return carpeta


@pytest.mark.parametrize("accion", ACCIONES_A_SIMULAR)
def test_simular_no_toca_disco_hash_identico(
    runner: CliRunner,
    mix_de_ficheros: Path,
    config_valida: Path,
    accion: str,
) -> None:
    """1) hash ANTES -> 2) --simular -> 3) hash DESPUÉS -> idénticos."""
    antes = tree_hash(mix_de_ficheros)

    resultado = llamar(
        runner, ["ejecutar", accion, str(mix_de_ficheros), "--simular"],
        config=config_valida,
    )
    salida = salida_normalizada(resultado.output)

    # La simulación termina OK y avisa explícitamente de que no ha escrito.
    assert resultado.exit_code == 0
    assert "simulación" in salida.lower()
    assert "no se ha modificado" in salida.lower()

    # La garantía de seguridad, medida en bytes: el árbol está IDENTICO.
    despues = tree_hash(mix_de_ficheros)
    assert despues == antes, (
        f"'--simular' ({accion}) modificó el árbol: "
        f"{antes[:12]}... != {despues[:12]}..."
    )
