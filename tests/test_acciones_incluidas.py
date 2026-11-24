"""Ejercita las acciones incluidas en acciones.json con archivos temporales."""
from pathlib import Path

import pytest
from typer.testing import CliRunner

from limpiador.cli import app

CONFIG = Path(__file__).resolve().parents[1] / "acciones.json"


@pytest.mark.parametrize("nombre", ["agrupar-audio", "archivar-imagenes-duplicadas"])
def test_acciones_propias(runner: CliRunner, tmp_path: Path, nombre: str) -> None:
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "tema.mp3").write_bytes(b"audio")
    (carpeta / "a.png").write_bytes(b"imagen")
    (carpeta / "b.png").write_bytes(b"imagen")
    base = ["--config", str(CONFIG), "ejecutar", nombre, str(carpeta)]
    sim = runner.invoke(app, [*base, "--simular"])
    assert sim.exit_code == 0, sim.output
    real = runner.invoke(app, [*base, "--si"])
    assert real.exit_code == 0, real.output
    if nombre == "agrupar-audio":
        assert (carpeta / "audio" / "tema.mp3").is_file()
    else:
        assert len(list(carpeta.glob("*.png"))) == 1
        assert len(list((carpeta / "papelera").rglob("*.png"))) == 1
        deshacer = runner.invoke(app, ["deshacer", "--carpeta", str(carpeta)])
        assert deshacer.exit_code == 0, deshacer.output
        assert len(list(carpeta.glob("*.png"))) == 2


@pytest.mark.parametrize("nombre", ["resumir-apuntes", "clasificar-ficheros"])
def test_acciones_ia_incluidas_sin_clave(runner: CliRunner, tmp_path: Path, nombre: str) -> None:
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "apuntes.txt").write_text("Tema de prueba. Otra frase.", encoding="utf-8")
    base = ["--config", str(CONFIG), "ejecutar", nombre, str(carpeta)]
    assert runner.invoke(app, [*base, "--simular"]).exit_code == 0
    real = runner.invoke(app, [*base, "--si"])
    assert real.exit_code == 4, real.output
    assert "modo offline" in real.output
