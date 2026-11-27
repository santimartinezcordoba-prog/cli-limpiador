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


def test_fallo_parcial_conserva_archivos_y_permite_deshacer(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    primero = carpeta / "a.png"
    segundo = carpeta / "b.png"
    primero.write_bytes(b"primero")
    segundo.write_bytes(b"segundo")
    config = escribir_config(tmp_path, CONFIG_VALIDA)
    replace_original = Path.replace

    def mover_con_fallo(self: Path, destino: Path) -> Path:
        if self == segundo:
            raise PermissionError("segundo archivo bloqueado")
        return replace_original(self, destino)

    with monkeypatch.context() as parche:
        parche.setattr(Path, "replace", mover_con_fallo)
        resultado = llamar(
            runner, ["ejecutar", "mover-imagenes", str(carpeta), "--si"], config=config
        )
    assert resultado.exit_code == EXIT_ERROR
    assert "fallo parcial" in salida_normalizada(resultado.output)
    assert (carpeta / "imagenes" / "a.png").read_bytes() == b"primero"
    assert segundo.read_bytes() == b"segundo"
    restaurado = llamar(runner, ["deshacer", "--carpeta", str(carpeta)])
    assert restaurado.exit_code == 0, restaurado.output
    assert primero.read_bytes() == b"primero"
    assert segundo.read_bytes() == b"segundo"


def test_enlace_roto_no_se_sobrescribe(runner: CliRunner, tmp_path: Path) -> None:
    carpeta = tmp_path / "pruebas"
    imagenes = carpeta / "imagenes"
    imagenes.mkdir(parents=True)
    (carpeta / "foto.png").write_bytes(b"original")
    enlace = imagenes / "foto.png"
    try:
        enlace.symlink_to(imagenes / "ausente.png")
    except OSError:
        pytest.skip("El sistema no permite crear enlaces simbólicos")
    config = escribir_config(tmp_path, CONFIG_VALIDA)
    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(carpeta), "--si"], config=config
    )
    assert resultado.exit_code == 0, resultado.output
    assert enlace.is_symlink()
    assert (imagenes / "foto-1.png").read_bytes() == b"original"
