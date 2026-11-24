"""Pruebas de los límites y del flujo obligatorio de simulación."""
from pathlib import Path

from typer.testing import CliRunner

from limpiador.cli import app


def ejecutar(runner: CliRunner, config: Path, carpeta: Path, *flags: str):
    return runner.invoke(app, ["--config", str(config), "ejecutar", "mover-imagenes",
                               str(carpeta), *flags])


def test_simulacion_obligatoria_y_un_solo_uso(runner, config_valida, carpeta_pruebas):
    foto = carpeta_pruebas / "foto.png"
    assert ejecutar(runner, config_valida, carpeta_pruebas, "--si").exit_code == 2
    assert foto.exists()
    assert ejecutar(runner, config_valida, carpeta_pruebas, "--simular").exit_code == 0
    assert ejecutar(runner, config_valida, carpeta_pruebas, "--si").exit_code == 0
    foto.write_text("nuevo", encoding="utf-8")
    assert ejecutar(runner, config_valida, carpeta_pruebas, "--si").exit_code == 2
    assert foto.exists()


def test_cambios_invalidan_simulacion(runner, config_valida, carpeta_pruebas):
    assert ejecutar(runner, config_valida, carpeta_pruebas, "--simular").exit_code == 0
    (carpeta_pruebas / "foto.png").write_text("contenido distinto", encoding="utf-8")
    assert ejecutar(runner, config_valida, carpeta_pruebas, "--si").exit_code == 2
    assert (carpeta_pruebas / "foto.png").exists()
    assert ejecutar(runner, config_valida, carpeta_pruebas, "--simular").exit_code == 0
    texto = config_valida.read_text(encoding="utf-8")
    config_valida.write_text(texto.replace("*.png", "*.gif"), encoding="utf-8")
    assert ejecutar(runner, config_valida, carpeta_pruebas, "--si").exit_code == 2


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
