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


@pytest.mark.parametrize(
    ("nombre", "prefijo", "esperado"),
    [
        ("crear-preguntas-repaso", "preguntas", "¿Qué significa o implica"),
        ("extraer-tareas-pendientes", "tareas", "Pendiente: entregar ejercicios"),
    ],
)
def test_nuevas_acciones_sin_red_y_simulacion(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    nombre: str, prefijo: str, esperado: str,
) -> None:
    from limpiador.ia import CentroIA

    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "notas.txt").write_text(
        "Las células contienen ADN.\nPendiente: entregar ejercicios", encoding="utf-8"
    )
    base = ["--config", str(CONFIG), "ejecutar", nombre, str(carpeta)]
    def no_red(*args: object, **kwargs: object) -> None:
        raise AssertionError("La simulación no debe contactar con el modelo")
    with monkeypatch.context() as parche:
        parche.setattr(CentroIA, "completar", no_red)
        simulacion = runner.invoke(app, [*base, "--simular"])
        assert simulacion.exit_code == 0, simulacion.output
        assert "caracteres al modelo" in simulacion.output
        assert not (carpeta / "resumenes").exists()
    real = runner.invoke(app, [*base, "--si"])
    assert real.exit_code == 4, real.output
    contenido = (carpeta / "resumenes" / f"{prefijo}-notas.md").read_text(encoding="utf-8")
    assert esperado in contenido


@pytest.mark.parametrize(
    ("nombre", "prefijo", "frase"),
    [
        ("crear-preguntas-repaso", "preguntas", "preguntas de repaso"),
        ("extraer-tareas-pendientes", "tareas", "tareas pendientes"),
    ],
)
def test_nuevas_acciones_con_proveedor_simulado(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    nombre: str, prefijo: str, frase: str,
) -> None:
    from limpiador.ia import CentroIA, RespuestaIA

    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "notas.txt").write_text("Primera frase. Pendiente: estudiar", encoding="utf-8")
    instrucciones: list[str] = []
    def completar(self: object, instruccion: str, **kwargs: object) -> RespuestaIA:
        instrucciones.append(instruccion)
        return RespuestaIA(contenido="resultado de prueba", latencia_s=0.1)
    monkeypatch.setattr(CentroIA, "completar", completar)
    base = ["--config", str(CONFIG), "ejecutar", nombre, str(carpeta)]
    sim = runner.invoke(app, [*base, "--simular"])
    assert sim.exit_code == 0, sim.output
    assert instrucciones == []
    real = runner.invoke(app, [*base, "--si"])
    assert real.exit_code == 0, real.output
    assert len(instrucciones) == 1
    assert frase in instrucciones[0]
    assert f"{len(instrucciones[0])} caracteres al modelo" in sim.output
    assert "resultado de prueba" in (carpeta / "resumenes" / f"{prefijo}-notas.md").read_text()
