"""Prueba estrella de seguridad: `--simular` NO toca el disco.

Demostración empírica con `tree_hash` (conftest): se fotografía el árbol
completo (rutas + contenidos) ANTES y DESPUÉS de simular y se exige que el
SHA256 sea IDÉNTICO. Si una sola implementación escribiera, renombrara o
creara una carpeta aunque fuera vacía, el hash cambiaría y el test estalla.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import llamar, salida_normalizada, tree_hash

# Acciones de CONFIG_VALIDA parametrizadas por operacion.
ACCIONES_A_SIMULAR = ("mover-imagenes", "borrar-temporales", "renombrar-viejos")

# Configuración extra: «borrar» con papelera activada y dedup. Ambas
# operaciones calculan en la planificación una ruta bajo
# `<carpeta>/papelera/<marca-temporal>/...`; si la planificación usara
# cualquier `mkdir()` o comprobación que creara carpetas «fantasma», el hash
# del árbol cambiaría y esta parametrización lo detectaría. CONFIG_VALIDA no
# cubre este caso porque allí `borrar-temporales` borra de forma definitiva.
CONFIG_PAPELERA_Y_DEDUP: dict[str, object] = {
    "version": 1,
    "acciones": [
        {
            "nombre": "borrar-temporales-papelera",
            "descripcion": "Borra .tmp moviéndolos a la papelera (reversible)",
            "operacion": "borrar",
            "patrones": ["*.tmp"],
            "papelera": True,
        },
        {
            "nombre": "dedup-fotos",
            "descripcion": "Archiva duplicados SHA256 de las imágenes",
            "operacion": "dedup",
            "patrones": ["*.png", "*.jpg"],
        },
    ],
}


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
    # Duplicado exacto de foto.png: garantiza que `dedup-fotos` tenga un
    # sobrante que planificar (si no hubiera duplicados, el plan sería vacío
    # y la prueba no ejercitaría la ruta a la papelera).
    (carpeta / "foto-copia.png").write_bytes(contenidos["foto.png"])
    sub = carpeta / "sub"
    sub.mkdir()
    (sub / "anidado.png").write_bytes(b"\x89PNG anidado")
    return carpeta


@pytest.fixture()
def config_papelera_dedup(tmp_path: Path) -> Path:
    """Config con `papelera: true` en borrar y una acción dedup."""
    ruta = tmp_path / "acciones-papelera.json"
    ruta.write_text(
        json.dumps(CONFIG_PAPELERA_Y_DEDUP, ensure_ascii=False), encoding="utf-8"
    )
    return ruta


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


@pytest.mark.parametrize(
    "accion",
    ("borrar-temporales-papelera", "dedup-fotos"),
)
def test_simular_con_papelera_no_crea_carpetas_fantasma(
    runner: CliRunner,
    mix_de_ficheros: Path,
    config_papelera_dedup: Path,
    accion: str,
) -> None:
    """Regression: simular una acción con papelera no debe crear NADA.

    La planificación de `borrar`+papelera y de `dedup` construye rutas
    dentro de `<carpeta>/papelera/<marca>/`. Si al calcular el destino libre
    se consultara el disco de forma que creara carpetas (p. ej. un `mkdir`
    en la ruta prevista), aparecerían directorios vacíos «fantasma» y el
    hash del árbol cambiaría. El smoke de CI (`find | sha256sum`) lo detectó
    en GitHub; este test lo fija localmente: hash idéntico + `papelera` no
    existe tras `--simular`.
    """
    antes = tree_hash(mix_de_ficheros)

    resultado = llamar(
        runner, ["ejecutar", accion, str(mix_de_ficheros), "--simular"],
        config=config_papelera_dedup,
    )
    assert resultado.exit_code == 0, resultado.output
    assert "no se ha modificado" in salida_normalizada(resultado.output).lower()

    despues = tree_hash(mix_de_ficheros)
    assert despues == antes, (
        f"'--simular' ({accion}) modificó el árbol: "
        f"{antes[:12]}... != {despues[:12]}..."
    )
    assert not (mix_de_ficheros / "papelera").exists()
