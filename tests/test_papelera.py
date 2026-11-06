"""Tests de la papelera de seguridad y de `limpiador deshacer`.

Regla de oro: todo ocurre dentro de `tmp_path`. La papelera vive DENTRO de
la carpeta objetivo (por defecto `<carpeta>/papelera/`), de modo que ni la
papelera ni su manifiesto pueden escribir fuera con path traversal.

Contrato probado:
- `borrar` con `"papelera": true` MUEVE a `papelera/<YYYYMMDD-HHMMSS>/` y
  escribe un manifiesto reversible en `papelera/.manifiesto/`.
- `deshacer [N]` restaura la ruta original; si el original existe, crea
  `nombre.restaurado.ext` y NO sobrescribe.
- Sin manifiesto o con borrados definitivos: `deshacer` sale con 1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from conftest import escribir_config, instantanea, llamar, salida_normalizada
from limpiador.cli import EXIT_CONFIG_INVALIDA, EXIT_ERROR, EXIT_OK

CONFIG_PAPELERA: dict[str, Any] = {
    "version": 1,
    "acciones": [
        {
            "nombre": "borrar-con-papelera",
            "descripcion": "Borra .tmp moviéndolos a la papelera (reversible)",
            "operacion": "borrar",
            "patrones": ["*.tmp"],
            "papelera": True,
        },
        {
            "nombre": "borrar-definitivo",
            "descripcion": "Borra .bak para siempre (sin papelera)",
            "operacion": "borrar",
            "patrones": ["*.bak"],
        },
        {
            "nombre": "papelera-personal",
            "descripcion": "Borra .log hacia una papelera con nombre propio",
            "operacion": "borrar",
            "patrones": ["*.log"],
            "papelera": "copia-seguridad",
        },
        {
            "nombre": "quitar-duplicados",
            "descripcion": "Mueve duplicados (mismo hash) a la papelera",
            "operacion": "dedup",
            "patrones": ["*.dat"],
        },
    ],
}


@pytest.fixture()
def config_papelera(tmp_path: Path) -> Path:
    return escribir_config(tmp_path, CONFIG_PAPELERA)


def _contenidos_papelera(papelera_base: Path) -> dict[str, bytes]:
    """Todos los ficheros de la papelera (sin el .manifiesto) por ruta relativa."""
    estado: dict[str, bytes] = {}
    for ruta in sorted(papelera_base.rglob("*")):
        if ruta.is_file() and ".manifiesto" not in ruta.parts:
            estado[str(ruta.relative_to(papelera_base))] = ruta.read_bytes()
    return estado


# --------------------------------------------------------------------------- #
# borrar + papelera = mover, no destruir
# --------------------------------------------------------------------------- #
def test_papelera_borrar_mueve_en_vez_de_borrar(
    runner: CliRunner, tmp_path: Path, config_papelera: Path
) -> None:
    """Con 'papelera': true el fichero NO desaparece: viaja a papelera/<ts>/."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "datos.tmp").write_bytes(b"contenido importante")

    resultado = llamar(
        runner, ["ejecutar", "borrar-con-papelera", str(objetivo), "--si"],
        config=config_papelera,
    )
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_OK
    # Ya no está en su sitio...
    assert not (objetivo / "datos.tmp").exists()
    # ...pero el contenido sigue vivo en papelera/<YYYYMMDD-HHMMSS>/datos.tmp.
    archivados = _contenidos_papelera(objetivo / "papelera")
    assert any(
        nombre.endswith("/datos.tmp") and contenido == b"contenido importante"
        for nombre, contenido in archivados.items()
    )
    # Y existe un manifiesto con el mapa origen -> destino.
    manifiestos = list((objetivo / "papelera" / ".manifiesto").glob("*.json"))
    assert len(manifiestos) == 1
    documento = json.loads(manifiestos[0].read_text(encoding="utf-8"))
    assert documento["accion"] == "borrar-con-papelera"
    assert documento["carpeta_base"] == str(objetivo.resolve())
    assert [set(entrada) for entrada in documento["entradas"]] == [{"origen", "destino"}]
    assert "deshacer" in salida  # la CLI te dice cómo revertir


# --------------------------------------------------------------------------- #
# deshacer: camino feliz
# --------------------------------------------------------------------------- #
def test_deshacer_restaura_ruta_original(
    runner: CliRunner, tmp_path: Path, config_papelera: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tras `--si` con papelera, `deshacer` devuelve el fichero a su sitio."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "datos.tmp").write_bytes(b"contenido importante")
    llamar(
        runner, ["ejecutar", "borrar-con-papelera", str(objetivo), "--si"],
        config=config_papelera,
    )
    assert not (objetivo / "datos.tmp").exists()

    monkeypatch.chdir(objetivo)
    resultado = llamar(runner, ["deshacer"], config=config_papelera)
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_OK
    assert (objetivo / "datos.tmp").is_file()
    assert (objetivo / "datos.tmp").read_bytes() == b"contenido importante"
    # La papelera queda vacía (salvo el manifiesto marcado como deshecha).
    assert _contenidos_papelera(objetivo / "papelera") == {}
    assert "Deshecha" in salida


def test_deshacer_revierte_tambien_un_mover(
    runner: CliRunner, tmp_path: Path, config_valida: Path
) -> None:
    """El manifiesto se escribe en toda ejecución --si: un `mover` también se deshace."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "foto.png").write_bytes(b"pixeles")
    llamar(
        runner, ["ejecutar", "mover-imagenes", str(objetivo), "--si"],
        config=config_valida,
    )
    assert (objetivo / "imagenes" / "foto.png").is_file()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(objetivo)
    resultado = llamar(runner, ["deshacer"], config=config_valida)
    monkeypatch.undo()

    assert resultado.exit_code == EXIT_OK
    assert (objetivo / "foto.png").is_file()
    assert not (objetivo / "imagenes" / "foto.png").exists()


# --------------------------------------------------------------------------- #
# deshacer: nunca sobrescribe
# --------------------------------------------------------------------------- #
def test_deshacer_no_sobrescribe_si_existe(
    runner: CliRunner, tmp_path: Path, config_papelera: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el original reaparece, se restaura como .restaurado sin tocarlo."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "datos.tmp").write_bytes(b"original")
    llamar(
        runner, ["ejecutar", "borrar-con-papelera", str(objetivo), "--si"],
        config=config_papelera,
    )
    # El usuario crea de nuevo un datos.tmp DIFFERENTE mientras tanto.
    (objetivo / "datos.tmp").write_bytes(b"nuevo e intocable")

    monkeypatch.chdir(objetivo)
    resultado = llamar(runner, ["deshacer"], config=config_papelera)
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_OK
    # El original nuevo queda INTACTO...
    assert (objetivo / "datos.tmp").read_bytes() == b"nuevo e intocable"
    # ...y el restaurado aparece con nombre .restaurado, avisando.
    restaurados = list(objetivo.glob("datos*.restaurado.tmp")) + list(
        objetivo.rglob("datos*.restaurado.tmp")
    )
    assert any(r.read_bytes() == b"original" for r in restaurados)
    assert "AVISO" in salida and ".restaurado" in salida


# --------------------------------------------------------------------------- #
# deshacer: casos feos -> exit 1
# --------------------------------------------------------------------------- #
def test_deshacer_sin_manifiesto_sale_1(
    runner: CliRunner, tmp_path: Path, config_papelera: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin papelera ni manifiestos, `deshacer` explica y sale con 1."""
    monkeypatch.chdir(tmp_path)

    resultado = llamar(runner, ["deshacer"], config=config_papelera)
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_ERROR
    assert "No se puede deshacer" in salida


def test_deshacer_borrado_definitivo_no_es_reversible(
    runner: CliRunner, tmp_path: Path, config_papelera: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un `borrar` sin papelera destruye datos: deshacer lo dice claro y sale 1."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "viejo.bak").write_bytes(b"basura")
    llamar(
        runner, ["ejecutar", "borrar-definitivo", str(objetivo), "--si"],
        config=config_papelera,
    )
    assert not (objetivo / "viejo.bak").exists()

    monkeypatch.chdir(objetivo)
    resultado = llamar(runner, ["deshacer"], config=config_papelera)
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_ERROR
    assert "no es reversible" in salida


def test_deshacer_n_inexistente_sale_1(
    runner: CliRunner, tmp_path: Path, config_papelera: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pedir la 5.ª operación cuando solo existe 1: error claro, exit 1."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "datos.tmp").write_bytes(b"x")
    llamar(
        runner, ["ejecutar", "borrar-con-papelera", str(objetivo), "--si"],
        config=config_papelera,
    )

    monkeypatch.chdir(objetivo)
    resultado = llamar(runner, ["deshacer", "5"], config=config_papelera)
    assert resultado.exit_code == EXIT_ERROR
    assert "no existe" in salida_normalizada(resultado.output)


# --------------------------------------------------------------------------- #
# Papelera con DIR personalizado y seguridad de rutas
# --------------------------------------------------------------------------- #
def test_papelera_dir_personalizada(
    runner: CliRunner, tmp_path: Path, config_papelera: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'papelera': 'copia-seguridad' usa <carpeta>/copia-seguridad/."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "servidor.log").write_bytes(b"log")

    llamar(
        runner, ["ejecutar", "papelera-personal", str(objetivo), "--si"],
        config=config_papelera,
    )
    archivados = _contenidos_papelera(objetivo / "copia-seguridad")
    assert any(nombre.endswith("/servidor.log") for nombre in archivados)

    # deshacer también la encuentra con --papelera.
    monkeypatch.chdir(objetivo)
    resultado = llamar(
        runner, ["deshacer", "1", "--papelera", "copia-seguridad"], config=config_papelera
    )
    assert resultado.exit_code == EXIT_OK
    assert (objetivo / "servidor.log").read_bytes() == b"log"


def test_papelera_path_traversal_se_rechaza(runner: CliRunner, tmp_path: Path) -> None:
    """Una papelera con '..' escribiría fuera: se rechaza al validar (exit 3)."""
    config = escribir_config(
        tmp_path,
        {
            "version": 1,
            "acciones": [
                {
                    "nombre": "mala",
                    "descripcion": "papelera fuera de la carpeta",
                    "operacion": "borrar",
                    "patrones": ["*.tmp"],
                    "papelera": "../huida",
                }
            ],
        },
    )

    resultado = llamar(runner, ["validar"], config=config)
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[0].papelera: debe ser una ruta relativa segura" in salida


def test_papelera_en_operacion_incompatible_se_rechaza(runner: CliRunner, tmp_path: Path) -> None:
    """'papelera' solo aplica a borrar/dedup: en 'mover' es error de validación."""
    config = escribir_config(
        tmp_path,
        {
            "version": 1,
            "acciones": [
                {
                    "nombre": "mala",
                    "descripcion": "papelera en mover",
                    "operacion": "mover",
                    "patrones": ["*.png"],
                    "destino": "imagenes",
                    "papelera": True,
                }
            ],
        },
    )

    resultado = llamar(runner, ["validar"], config=config)
    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "solo aplica a las operaciones 'borrar' o 'dedup'" in salida_normalizada(
        resultado.output
    )


# --------------------------------------------------------------------------- #
# dedup: duplicados a la papelera (siempre reversible)
# --------------------------------------------------------------------------- #
def test_dedup_mueve_duplicados_a_papelera_y_deshacer_restaura(
    runner: CliRunner, tmp_path: Path, config_papelera: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De dos ficheros idénticos se queda uno; el duplicado va a papelera."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "a.dat").write_bytes(b"mismo contenido")
    (objetivo / "b.dat").write_bytes(b"mismo contenido")
    (objetivo / "unico.dat").write_bytes(b"otro contenido")

    resultado = llamar(
        runner, ["ejecutar", "quitar-duplicados", str(objetivo), "--si"],
        config=config_papelera,
    )

    assert resultado.exit_code == EXIT_OK
    assert (objetivo / "a.dat").is_file()  # el primero se conserva
    assert not (objetivo / "b.dat").exists()
    assert (objetivo / "unico.dat").is_file()  # lo único, intacto
    archivados = _contenidos_papelera(objetivo / "papelera")
    assert any(nombre.endswith("/b.dat") for nombre in archivados)

    monkeypatch.chdir(objetivo)
    resultado = llamar(runner, ["deshacer"], config=config_papelera)
    assert resultado.exit_code == EXIT_OK
    assert (objetivo / "b.dat").read_bytes() == b"mismo contenido"


# --------------------------------------------------------------------------- #
# Simulación: ni la papelera se crea
# --------------------------------------------------------------------------- #
def test_simular_papelera_no_crea_nada(
    runner: CliRunner, tmp_path: Path, config_papelera: Path
) -> None:
    """--simular con papelera activada no crea papelera ni manifiesto."""
    objetivo = tmp_path / "destino"
    objetivo.mkdir()
    (objetivo / "datos.tmp").write_bytes(b"x")
    antes = instantanea(objetivo)

    resultado = llamar(
        runner, ["ejecutar", "borrar-con-papelera", str(objetivo), "--simular"],
        config=config_papelera,
    )
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_OK
    assert "papelera" in salida  # el plan menciona el destino
    assert instantanea(objetivo) == antes
