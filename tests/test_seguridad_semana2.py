"""Pruebas de los límites y del flujo obligatorio de simulación."""
from pathlib import Path

from typer.testing import CliRunner

from limpiador.cli import app


def ejecutar(runner: CliRunner, config: Path, carpeta: Path, *flags: str):
    return runner.invoke(app, ["--config", str(config), "ejecutar", "mover-imagenes",
                               str(carpeta), *flags])


def test_simulacion_no_escribe_ningun_archivo(runner, config_valida, carpeta_pruebas, monkeypatch):
    # Prohibir llamadas a las primitivas de escritura, incluso fuera del objetivo.
    import io
    import os

    abrir = io.open
    abrir_os = os.open

    def prohibido(*args, **kwargs):
        raise AssertionError("La simulación intentó escribir")

    def abrir_solo_lectura(archivo, modo="r", *args, **kwargs):
        if any(c in modo for c in "wax+"):
            prohibido()
        return abrir(archivo, modo, *args, **kwargs)

    def abrir_os_solo_lectura(ruta, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            prohibido()
        return abrir_os(ruta, flags, *args, **kwargs)

    monkeypatch.setattr(io, "open", abrir_solo_lectura)
    monkeypatch.setattr(os, "open", abrir_os_solo_lectura)
    monkeypatch.setattr(Path, "write_text", prohibido)
    monkeypatch.setattr(Path, "write_bytes", prohibido)
    monkeypatch.setattr(Path, "mkdir", prohibido)
    resultado = ejecutar(runner, config_valida, carpeta_pruebas, "--simular")
    assert resultado.exit_code == 0, resultado.output
    assert (carpeta_pruebas / "foto.png").is_file()


def test_ejecucion_muestra_simulacion_actual(runner, config_valida, carpeta_pruebas):
    resultado = ejecutar(runner, config_valida, carpeta_pruebas, "--si")
    assert resultado.exit_code == 0, resultado.output
    assert "simula" in resultado.output.lower()
    assert (carpeta_pruebas / "imagenes" / "foto.png").is_file()


def test_cambio_durante_confirmacion_impide_ejecutar(
    runner, config_valida, carpeta_pruebas, monkeypatch
):
    monkeypatch.setattr("limpiador.cli._stdin_interactivo", lambda: True)
    def cambiar(*args):
        (carpeta_pruebas / "foto.png").write_text("cambiado", encoding="utf-8")
    monkeypatch.setattr("limpiador.cli._pedir_confirmacion_o_salir", cambiar)
    resultado = ejecutar(runner, config_valida, carpeta_pruebas)
    assert resultado.exit_code == 2
    assert (carpeta_pruebas / "foto.png").exists()
    assert not (carpeta_pruebas / "imagenes").exists()


def test_fuera_y_enlace_fuera_denegados(runner, config_valida, tmp_path):
    fuera = tmp_path.parent / (tmp_path.name + "-fuera")
    fuera.mkdir()
    (fuera / "foto.png").write_text("sin tocar", encoding="utf-8")
    enlace = tmp_path / "enlace"
    enlace.symlink_to(fuera, target_is_directory=True)
    for carpeta in (fuera, enlace):
        resultado = ejecutar(runner, config_valida, carpeta, "--simular")
        assert resultado.exit_code == 1
        assert "pruebas-tareas" in resultado.output
        resultado = runner.invoke(app, ["deshacer", "--carpeta", str(carpeta)])
        assert resultado.exit_code == 1
    assert (fuera / "foto.png").read_text(encoding="utf-8") == "sin tocar"
