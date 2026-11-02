"""Tests de `limpiador validar`: config válida y todos los casos de error.

Se comprueba el contrato del exit code 3 y los mensajes exactos del estilo
``acciones[0].nombre: campo requerido``.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CONFIG_VALIDA, escribir_config, llamar
from limpiador.cli import EXIT_CONFIG_INVALIDA, EXIT_OK


def test_config_valida_sale_con_cero(runner: CliRunner, tmp_path: Path) -> None:
    """Con un JSON correcto, `validar` responde 'válido' y sale con código 0."""
    config = escribir_config(tmp_path, CONFIG_VALIDA)

    resultado = llamar(runner, ["validar"], config=config)

    assert resultado.exit_code == EXIT_OK
    assert "válido" in resultado.output


def test_por_defecto_usa_acciones_json_del_cwd(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin --config, la CLI busca ./acciones.json en el directorio actual."""
    escribir_config(tmp_path, CONFIG_VALIDA)  # se llama justo 'acciones.json'
    monkeypatch.chdir(tmp_path)

    resultado = llamar(runner, ["validar"])  # sin opción --config

    assert resultado.exit_code == EXIT_OK


def test_config_inexistente(runner: CliRunner, tmp_path: Path) -> None:
    """Si el fichero no existe, error claro y código 3."""
    resultado = llamar(runner, ["validar"], config=tmp_path / "nadie.json")

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "no existe" in resultado.output


def test_json_mal_formado(runner: CliRunner, tmp_path: Path) -> None:
    """Caso feo 1: JSON corrupto -> exit code 3 y mensaje con la línea exacta."""
    config = escribir_config(tmp_path, '{"version": 1, "acciones": [ { SIN CERRAR')

    resultado = llamar(runner, ["validar"], config=config)

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    # El usuario ve que el JSON está roto y dónde (línea y columna).
    assert "JSON mal formado" in resultado.output
    assert "línea" in resultado.output


def test_falta_la_lista_de_acciones(runner: CliRunner, tmp_path: Path) -> None:
    """Sin la clave 'acciones' no hay nada que hacer: fallo y código 3."""
    config = escribir_config(tmp_path, {"version": 1})

    resultado = llamar(runner, ["validar"], config=config)

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones: campo requerido" in resultado.output


def test_accion_sin_nombre(runner: CliRunner, tmp_path: Path) -> None:
    """Falta 'nombre' -> el error debe señalar acciones[0].nombre."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    del datos["acciones"][0]["nombre"]

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[0].nombre: campo requerido" in resultado.output


def test_accion_sin_descripcion(runner: CliRunner, tmp_path: Path) -> None:
    """Falta 'descripcion' -> se reporta la ruta exacta del campo."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    del datos["acciones"][1]["descripcion"]

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[1].descripcion: campo requerido" in resultado.output


def test_operacion_no_soportada(runner: CliRunner, tmp_path: Path) -> None:
    """Una operación desconocida ('comprimir') no está soportada."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    datos["acciones"][1]["operacion"] = "comprimir"

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[1].operacion: valor no soportado" in resultado.output


def test_mover_sin_destino(runner: CliRunner, tmp_path: Path) -> None:
    """La operación 'mover' exige 'destino'; sin él, error específico."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    del datos["acciones"][0]["destino"]

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[0].destino: campo requerido" in resultado.output


def test_accion_sin_patrones(runner: CliRunner, tmp_path: Path) -> None:
    """Sin 'patrones' la acción no sabría qué ficheros coger."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    del datos["acciones"][2]["patrones"]

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[2].patrones: campo requerido" in resultado.output


def test_patron_con_path_traversal(runner: CliRunner, tmp_path: Path) -> None:
    """Un patrón con '..' intentaría salir de la carpeta: se rechaza."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    datos["acciones"][0]["patrones"] = ["../*.png"]

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[0].patrones[0]: patrón inválido o no seguro" in resultado.output


def test_destino_con_path_traversal(runner: CliRunner, tmp_path: Path) -> None:
    """Un destino '../fuera' escribiría fuera de la carpeta: se rechaza."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    datos["acciones"][0]["destino"] = "../fuera"

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[0].destino: debe ser una ruta relativa segura" in resultado.output


def test_varios_errores_se_reportan_a_la_vez(runner: CliRunner, tmp_path: Path) -> None:
    """El validador no se para en el primer fallo: lista todos de golpe."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    del datos["acciones"][0]["nombre"]  # error 1
    datos["acciones"][1]["operacion"] = "volar"  # error 2

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[0].nombre: campo requerido" in resultado.output
    assert "acciones[1].operacion: valor no soportado" in resultado.output


def test_acciones_replicadas_se_detectan(runner: CliRunner, tmp_path: Path) -> None:
    """Dos acciones con el mismo nombre harían ambiguous `ejecutar`: se rechaza."""
    datos = copy.deepcopy(CONFIG_VALIDA)
    datos["acciones"][1]["nombre"] = datos["acciones"][0]["nombre"]

    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))

    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "nombre duplicado" in resultado.output
