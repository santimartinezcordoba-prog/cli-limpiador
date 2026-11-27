"""Regresiones detectadas al revisar la rúbrica final."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CONFIG_VALIDA, escribir_config, llamar, salida_normalizada
from limpiador.acciones import Motor
from limpiador.config import cargar_dotenv
from limpiador.errores import EXIT_CONFIG_INVALIDA, EXIT_ERROR


@pytest.mark.parametrize("destino", [r"C:\fuera", "C:fuera", r"\fuera", r"\\servidor\share"])
def test_destino_windows_invalido(
    runner: CliRunner, tmp_path: Path, destino: str
) -> None:
    datos = copy.deepcopy(CONFIG_VALIDA)
    datos["acciones"][0]["destino"] = destino
    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))
    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[0].destino" in salida_normalizada(resultado.output)


@pytest.mark.parametrize("patron", ["sub/*.txt", r"sub\*.txt", "   ", "a\0.txt"])
def test_patron_invalido(runner: CliRunner, tmp_path: Path, patron: str) -> None:
    datos = copy.deepcopy(CONFIG_VALIDA)
    datos["acciones"][0]["patrones"] = [patron]
    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))
    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "acciones[0].patrones[0]" in salida_normalizada(resultado.output)


def test_nombre_duplicado_con_espacios(runner: CliRunner, tmp_path: Path) -> None:
    datos = copy.deepcopy(CONFIG_VALIDA)
    datos["acciones"][1]["nombre"] = " " + datos["acciones"][0]["nombre"] + " "
    resultado = llamar(runner, ["validar"], config=escribir_config(tmp_path, datos))
    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "nombre duplicado" in salida_normalizada(resultado.output)


def test_json_no_utf8(runner: CliRunner, tmp_path: Path) -> None:
    ruta = tmp_path / "acciones.json"
    ruta.write_bytes(b"\xff")
    resultado = llamar(runner, ["validar"], config=ruta)
    assert resultado.exit_code == EXIT_CONFIG_INVALIDA
    assert "UTF-8" in salida_normalizada(resultado.output)


def test_env_no_utf8(tmp_path: Path) -> None:
    ruta = tmp_path / ".env"
    ruta.write_bytes(b"\xff")
    assert cargar_dotenv(ruta) is None


def test_error_de_disco_en_simulacion(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    archivo = carpeta / "foto.png"
    archivo.write_bytes(b"original")

    def fallar(*args: object, **kwargs: object) -> None:
        raise PermissionError("permiso denegado de prueba")

    monkeypatch.setattr(Motor, "planificar", fallar)
    resultado = llamar(
        runner,
        ["ejecutar", CONFIG_VALIDA["acciones"][0]["nombre"], str(carpeta), "--simular"],
        config=escribir_config(tmp_path, CONFIG_VALIDA),
    )
    assert resultado.exit_code == EXIT_ERROR
    assert "permiso denegado de prueba" in salida_normalizada(resultado.output)
    assert archivo.read_bytes() == b"original"
    assert list(carpeta.iterdir()) == [archivo]
