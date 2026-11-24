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


def test_mover_y_deduplicar_en_carpeta_de_destino(runner: CliRunner, tmp_path: Path) -> None:
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "foto.JPG").write_bytes(b"imagen")
    (carpeta / "copia.PNG").write_bytes(b"imagen")
    mover = ["--config", str(CONFIG), "ejecutar", "mover-imagenes", str(carpeta)]
    assert runner.invoke(app, [*mover, "--simular"]).exit_code == 0
    resultado = runner.invoke(app, [*mover, "--si"])
    assert resultado.exit_code == 0, resultado.output
    imagenes = carpeta / "imagenes"
    assert (imagenes / "foto.JPG").exists()
    assert (imagenes / "copia.PNG").exists()
    dedup = ["--config", str(CONFIG), "ejecutar", "archivar-imagenes-duplicadas", str(imagenes)]
    resultado = runner.invoke(app, [*dedup, "--si"])
    assert resultado.exit_code == 0, resultado.output
    assert len([p for p in imagenes.iterdir() if p.is_file()]) == 1
    assert len([p for p in (imagenes / "papelera").rglob("*") if p.suffix in {".JPG", ".PNG"}]) == 1


def test_renombrar_incluido_no_repite_sufijo(runner: CliRunner, tmp_path: Path) -> None:
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "nota.TXT").write_text("contenido", encoding="utf-8")
    base = ["--config", str(CONFIG), "ejecutar", "renombrar-viejos", str(carpeta), "--si"]
    primero = runner.invoke(app, base)
    assert primero.exit_code == 0, primero.output
    assert (carpeta / "nota-revisar.TXT").exists()
    segundo = runner.invoke(app, base)
    assert segundo.exit_code == 0, segundo.output
    assert (carpeta / "nota-revisar.TXT").exists()
    assert not (carpeta / "nota-revisar-revisar.TXT").exists()


def test_validar_accion_ia_con_destino_muestra_regla(runner: CliRunner, tmp_path: Path) -> None:
    import json

    config = tmp_path / "acciones.json"
    config.write_text(json.dumps({"version": 1, "acciones": [{
        "nombre": "resumir", "descripcion": "Resumen", "operacion": "resumir-texto",
        "patrones": ["*.txt"], "modelo": "modelo", "destino": "salida",
    }]}), encoding="utf-8")
    resultado = runner.invoke(app, ["--config", str(config), "validar"])
    assert resultado.exit_code == 3
    assert "'destino' solo aplica a la operación 'mover'" in resultado.output
