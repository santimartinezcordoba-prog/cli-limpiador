"""Camino feliz de la CLI: ayuda, version, listar y acciones.

Cada test usa `tmp_path` (carpeta temporal de pytest). Ninguno toca
ficheros reales del ordenador.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import instantanea, llamar
from limpiador import __version__
from limpiador.cli import EXIT_ERROR


def test_ayuda_enumera_todas_las_ordenes(runner: CliRunner) -> None:
    """`limpiador --help` debe listar todas las órdenes y la opción --config."""
    resultado = llamar(runner, ["--help"])

    # La ayuda general siempre debe funcionar.
    assert resultado.exit_code == 0
    # Todas las órdenes obligatorias aparecen en la ayuda.
    for orden in ("version", "listar", "acciones", "validar", "ejecutar"):
        assert orden in resultado.output, f"la orden '{orden}' no aparece en --help"
    # La opción global --config también debe documentarse.
    assert "--config" in resultado.output


def test_version_muestra_la_version_instalada(runner: CliRunner) -> None:
    """`limpiador version` imprime la versión del paquete instalado.

    Se compara con `limpiador.__version__` (leída de los metadatos con
    importlib.metadata), no con un número fijo: así el test sigue valiendo
    cuando se suba de versión.
    """
    resultado = llamar(runner, ["version"])

    assert resultado.exit_code == 0
    assert __version__ in resultado.output


def test_listar_muestra_nombre_tipo_tamano_y_fecha(
    runner: CliRunner, carpeta_pruebas: Path
) -> None:
    """`limpiador listar` pinta una tabla con los ficheros de la carpeta."""
    resultado = llamar(runner, ["listar", str(carpeta_pruebas)])

    assert resultado.exit_code == 0
    # Deben verse los ficheros creados en la carpeta temporal...
    for nombre in ("foto.png", "selfie.jpg", "informe.pdf", "nota.docx", "datos.tmp"):
        assert nombre in resultado.output, f"'{nombre}' no aparece en la tabla"
    # ...y las cabeceras de las columnas exigidas.
    assert "Nombre" in resultado.output
    assert "Tipo" in resultado.output
    assert "Tamaño" in resultado.output
    assert "Modificado" in resultado.output


def test_listar_no_modifica_nada(
    runner: CliRunner, carpeta_pruebas: Path
) -> None:
    """`listar` es de solo lectura: el contenido de la carpeta es idéntico."""
    antes = instantanea(carpeta_pruebas)

    llamar(runner, ["listar", str(carpeta_pruebas)])

    # La instantánea (rutas + contenidos) no cambia ni un byte.
    assert instantanea(carpeta_pruebas) == antes


def test_listar_carpeta_inexistente_da_error_claro(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Caso feo 3: una carpeta que no existe debe dar error claro y código 1."""
    ruta_falsa = tmp_path / "no-existe"

    resultado = llamar(runner, ["listar", str(ruta_falsa)])

    assert resultado.exit_code == EXIT_ERROR
    # El mensaje debe decir el problema y la carpeta implicada.
    assert "no existe" in resultado.output
    assert "no-existe" in resultado.output


def test_listar_por_defecto_usa_la_carpeta_actual(
    runner: CliRunner, carpeta_pruebas: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin argumento CARPETA, `listar` trabaja sobre el directorio actual."""
    monkeypatch.chdir(carpeta_pruebas)

    resultado = llamar(runner, ["listar"])

    assert resultado.exit_code == 0
    # Al estar dentro de la carpeta de pruebas, sus ficheros aparecen.
    assert "foto.png" in resultado.output


def test_acciones_lista_todas_las_acciones_con_descripcion(
    runner: CliRunner, config_valida: Path
) -> None:
    """`limpiador acciones` muestra nombre, operación y descripción de cada una."""
    resultado = llamar(runner, ["acciones"], config=config_valida)

    assert resultado.exit_code == 0
    # Cada acción del JSON debe verse con su nombre y su descripción.
    for accion in ("mover-imagenes", "borrar-temporales", "ordenar-documentos"):
        assert accion in resultado.output
    assert "Mueve imágenes a una carpeta imagenes/" in resultado.output


def test_acciones_con_config_alternativa(
    runner: CliRunner, tmp_path: Path, config_valida: Path
) -> None:
    """La opción global --config permite usar otro fichero de acciones.

    Se crea un segundo JSON (`acciones-personales.json`) y se comprueba que
    la CLI lee de ese y no del ./acciones.json por defecto.
    """
    personal = tmp_path / "acciones-personales.json"
    personal.write_text(
        '{"version": 1, "acciones": [{"nombre": "mi-accion-solo-mia",'
        ' "descripcion": "prueba", "operacion": "borrar", "patrones": ["*.bak"]}]}',
        encoding="utf-8",
    )
    # Si fallara el --config, leería el JSON por defecto (config_valida)
    # y "mi-accion-solo-mia" no aparecería nunca.
    assert config_valida.is_file()

    resultado = llamar(runner, ["acciones"], config=personal)

    assert resultado.exit_code == 0
    assert "mi-accion-solo-mia" in resultado.output
    assert "mover-imagenes" not in resultado.output
