"""La IA no escribe mediante enlaces simbólicos hacia otras carpetas."""
from pathlib import Path

import pytest
from typer.testing import CliRunner

from limpiador.cli import app

CONFIG = Path(__file__).resolve().parents[1] / "acciones.json"


def crear_enlace(origen: Path, destino: Path, directorio: bool = False) -> None:
    try:
        origen.symlink_to(destino, target_is_directory=directorio)
    except (OSError, NotImplementedError):
        pytest.skip("El sistema no permite crear enlaces simbólicos")


@pytest.mark.parametrize("nombre", ["resumir-apuntes", "clasificar-ficheros"])
def test_rechaza_directorio_resumenes_enlazado(
    runner: CliRunner, tmp_path: Path, nombre: str
) -> None:
    raiz = tmp_path / "pruebas"
    raiz.mkdir()
    exterior = tmp_path / "exterior"
    exterior.mkdir()
    (raiz / "apuntes.txt").write_text("contenido", encoding="utf-8")
    crear_enlace(raiz / "resumenes", exterior, True)
    resultado = runner.invoke(app, ["--config", str(CONFIG), "ejecutar", nombre, str(raiz), "--si"])
    assert resultado.exit_code == 1, resultado.output
    assert list(exterior.iterdir()) == []


def test_rechaza_log_enlazado(runner: CliRunner, tmp_path: Path) -> None:
    raiz = tmp_path / "pruebas"
    raiz.mkdir()
    (raiz / "resumenes").mkdir()
    exterior = tmp_path / "fuera.txt"
    exterior.write_text("no modificar", encoding="utf-8")
    (raiz / "apuntes.txt").write_text("contenido", encoding="utf-8")
    crear_enlace(raiz / "resumenes" / "log_ia.md", exterior)
    resultado = runner.invoke(
        app, ["--config", str(CONFIG), "ejecutar", "resumir-apuntes", str(raiz), "--si"]
    )
    assert resultado.exit_code == 1, resultado.output
    assert exterior.read_text(encoding="utf-8") == "no modificar"
    assert not (raiz / "resumenes" / "resumen-apuntes.md").exists()
