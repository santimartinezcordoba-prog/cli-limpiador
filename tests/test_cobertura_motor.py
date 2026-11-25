"""Casos límite del motor y configuración, sin red ni datos reales."""

from __future__ import annotations

from pathlib import Path

import pytest

from limpiador.acciones import (
    AccionPlanificadora,
    Operacion,
    comprobar_carpeta_resuelta,
    ejecutar,
    planificar,
    planificar_desde_objetivos,
)
from limpiador.config import Accion, cargar_config, cargar_dotenv, env_relevantes, validar_contenido
from limpiador.errores import AccionError, ConfigInvalidaError, PapeleraError
from limpiador.papelera import (
    EntradaManifiesto,
    deshacer_operacion,
    escribir_manifiesto,
    listar_manifiestos,
    resolver_papelera_cli,
)


def accion(operacion: str = "borrar", **campos: object) -> Accion:
    datos = {"nombre": "prueba", "descripcion": "Prueba", "operacion": operacion,
             "patrones": ["*.txt"], **campos}
    return Accion.model_validate(datos)


@pytest.mark.parametrize("datos", [
    None, [], 3, {"acciones": [3]}, {"acciones": {}}, {"acciones": []},
    {"version": "1", "acciones": [{"nombre": "x"}]},
    {"version": 1, "acciones": [{"nombre": "x", "desconocido": 1}]},
])
def test_config_formas_invalidas(datos: object) -> None:
    with pytest.raises(ConfigInvalidaError) as exc:
        validar_contenido(datos)
    assert exc.value.errores
    assert all(isinstance(mensaje, str) for mensaje in exc.value.errores)


@pytest.mark.parametrize("campo, valor", [
    ("papelera", ""), ("sufijo", "../x"), ("sufijo", "x"),
    ("modelo", "M"), ("prompt", "instrucción"), ("operacion", 2),
    ("patrones", "texto"), ("patrones", []), ("patrones", [1]),
    ("patrones", [""]), ("patrones", ["/fuera"]), ("patrones", ["~"]),
    ("descripcion", ""), ("nombre", ""), ("modo_offline", "incorrecto"),
])
def test_config_campos_invalidos(campo: str, valor: object) -> None:
    datos = {"nombre": "x", "descripcion": "prueba", "operacion": "borrar",
             "patrones": ["*.txt"], campo: valor}
    with pytest.raises(ConfigInvalidaError) as exc:
        validar_contenido({"acciones": [datos]})
    assert any("acciones[0]" in mensaje for mensaje in exc.value.errores)


def test_config_directorio(tmp_path: Path) -> None:
    with pytest.raises(ConfigInvalidaError, match="no es un fichero"):
        cargar_config(tmp_path)


def test_config_lectura_fallida(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ruta = tmp_path / "acciones.json"
    ruta.write_text("{}", encoding="utf-8")

    def denegar(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError("lectura denegada")

    monkeypatch.setattr(Path, "read_text", denegar)
    with pytest.raises(ConfigInvalidaError, match="no se pudo leer"):
        cargar_config(ruta)


def test_dotenv_ilegible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ruta = tmp_path / ".env"
    ruta.touch()

    def denegar(self: Path, *args: object, **kwargs: object) -> str:
        raise PermissionError("lectura denegada")

    monkeypatch.setattr(Path, "read_text", denegar)
    assert cargar_dotenv(ruta) is None


def test_dotenv_lineas_y_entorno(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for nombre in ("LIMPIADOR_IA_MODELO", "LIMPIADOR_IA_KEY", "LIMPIADOR_IA_TIMEOUT"):
        monkeypatch.delenv(nombre, raising=False)
    ruta = tmp_path / ".env"
    ruta.write_text(
        "# comentario\n\nlínea inválida\nexport LIMPIADOR_IA_MODELO='M'\n"
        "LIMPIADOR_IA_TIMEOUT=3\n", encoding="utf-8",
    )
    assert cargar_dotenv(ruta) == ruta
    entorno = env_relevantes()
    assert entorno["LIMPIADOR_IA_MODELO"] == "M"
    assert entorno["LIMPIADOR_IA_TIMEOUT"] == "3"
    assert env_relevantes({
        "LIMPIADOR_IA_KEY": "valor ficticio", "LIMPIADOR_IA_MODELO": "M", "HOME": "x",
    }) == {"LIMPIADOR_IA_KEY": "<presente>", "LIMPIADOR_IA_MODELO": "M"}


def test_motor_rechaza_carpeta_invalida(tmp_path: Path) -> None:
    fichero = tmp_path / "f.txt"
    fichero.touch()
    for ruta in (tmp_path / "ausente", fichero, Path(tmp_path.anchor)):
        with pytest.raises(AccionError):
            comprobar_carpeta_resuelta(ruta)


def test_planificador_desconocido() -> None:
    invalida = accion().model_copy(update={"operacion": "no-existe"})
    with pytest.raises(AccionError, match="operación desconocida"):
        AccionPlanificadora.desde_config(invalida)


def test_colisiones_mover(tmp_path: Path) -> None:
    origen = tmp_path / "f.txt"
    origen.write_text("nuevo", encoding="utf-8")
    destino = tmp_path / "destino"
    destino.mkdir()
    (destino / "f.txt").write_text("original", encoding="utf-8")
    config = accion("mover", destino="destino")
    plan = planificar(config, tmp_path)
    assert plan[0].destino == destino / "f-1.txt"
    (destino / "f-1.txt").write_text("otro", encoding="utf-8")
    ejecutar(config, tmp_path, plan)
    assert (destino / "f-1-1.txt").read_text(encoding="utf-8") == "nuevo"
    assert (destino / "f.txt").read_text(encoding="utf-8") == "original"
    assert (destino / "f-1.txt").read_text(encoding="utf-8") == "otro"


def test_mover_misma_carpeta(tmp_path: Path) -> None:
    fichero = tmp_path / "f.txt"
    fichero.touch()
    config = accion("mover", destino=".")
    assert planificar_desde_objetivos(config, tmp_path, [fichero]) == []
    assert ejecutar(config, tmp_path, []) == ([], None)
    assert fichero.is_file()


def test_renombrar_colision_y_ya_renombrado(tmp_path: Path) -> None:
    origen = tmp_path / "f.txt"
    origen.touch()
    (tmp_path / "f-revisar.txt").touch()
    config = accion("renombrar", sufijo="revisar")
    plan = planificar(config, tmp_path)
    assert len(plan) == 1
    assert plan[0].destino == tmp_path / "f-revisar-1.txt"
    ejecutar(config, tmp_path, plan)
    assert (tmp_path / "f-revisar-1.txt").exists()


def test_papelera_colision_simulada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    origen = tmp_path / "f.txt"
    origen.write_text("nuevo", encoding="utf-8")
    monkeypatch.setattr("limpiador.acciones.nueva_marca_temporal", lambda: "marca")
    destino = tmp_path / "papelera" / "marca"
    destino.mkdir(parents=True)
    (destino / "f.txt").touch()
    plan = planificar(accion(papelera=True), tmp_path)
    assert plan[0].destino == destino / "f-1.txt"
    assert origen.exists()


def test_dedup_lectura_denegada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "f.txt").touch()

    def denegar(self: Path) -> bytes:
        raise PermissionError("lectura denegada")

    monkeypatch.setattr(Path, "read_bytes", denegar)
    with pytest.raises(AccionError, match="no se pudo leer"):
        planificar(accion("dedup"), tmp_path)


def test_motor_plan_fuera_de_raiz(tmp_path: Path) -> None:
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    externo = tmp_path / "externo.txt"
    externo.touch()
    interno = raiz / "f.txt"
    interno.touch()
    for paso in (Operacion("borrar", externo), Operacion("mover", interno, externo)):
        with pytest.raises(AccionError, match="fuera"):
            ejecutar(accion(), raiz, [paso])
    assert externo.exists() and interno.exists()


def test_motor_no_ejecuta_plan_ia(tmp_path: Path) -> None:
    config = accion("resumir-texto", modelo="M")
    fichero = tmp_path / "f.txt"
    fichero.touch()
    plan = planificar(config, tmp_path)
    with pytest.raises(AccionError, match="motor de IA"):
        ejecutar(config, tmp_path, plan)


def test_destino_enlace_fuera(tmp_path: Path) -> None:
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (raiz / "f.txt").touch()
    try:
        (raiz / "destino").symlink_to(fuera, target_is_directory=True)
    except OSError:
        pytest.skip("Enlaces simbólicos no disponibles")
    with pytest.raises(AccionError, match="fuera"):
        planificar(accion("mover", destino="destino"), raiz)
    assert not list(fuera.iterdir())


def registrar(raiz: Path, origen: Path, destino: Path) -> Path:
    return escribir_manifiesto(
        papelera_base=raiz / "papelera", op_id="prueba", accion="prueba",
        operacion="mover", carpeta_base=raiz,
        entradas=[EntradaManifiesto(origen, destino)], timestamp="2026-11-25T10:00:00",
    )


def test_manifiesto_corrupto_y_ausente(tmp_path: Path) -> None:
    carpeta = tmp_path / "papelera" / ".manifiesto"
    carpeta.mkdir(parents=True)
    (carpeta / "roto.json").write_text("{", encoding="utf-8")
    (carpeta / "incompleto.json").write_text("{}", encoding="utf-8")
    assert listar_manifiestos(carpeta.parent) == []
    with pytest.raises(PapeleraError, match="no hay operaciones"):
        deshacer_operacion(carpeta.parent, carpeta_base=tmp_path)


def test_restauracion_archivo_ausente(tmp_path: Path) -> None:
    registrar(tmp_path, tmp_path / "origen.txt", tmp_path / "no-existe.txt")
    with pytest.raises(PapeleraError, match="ya no está"):
        deshacer_operacion(tmp_path / "papelera", carpeta_base=tmp_path)


def test_restauracion_colision_multiple(tmp_path: Path) -> None:
    origen = tmp_path / "f.txt"
    origen.write_text("actual", encoding="utf-8")
    (tmp_path / "f.restaurado.txt").touch()
    (tmp_path / "f.restaurado-1.txt").touch()
    archivado = tmp_path / "archivo.txt"
    archivado.write_text("anterior", encoding="utf-8")
    registrar(tmp_path, origen, archivado)
    deshacer_operacion(tmp_path / "papelera", carpeta_base=tmp_path)
    assert origen.read_text(encoding="utf-8") == "actual"
    assert (tmp_path / "f.restaurado-2.txt").read_text(encoding="utf-8") == "anterior"
    assert listar_manifiestos(tmp_path / "papelera") == []


def test_papelera_parametros_invalidos(tmp_path: Path) -> None:
    with pytest.raises(PapeleraError, match="positivo"):
        deshacer_operacion(tmp_path / "papelera", 0, carpeta_base=tmp_path)
    with pytest.raises(PapeleraError, match="ruta relativa"):
        resolver_papelera_cli(tmp_path, "../fuera")


def test_restauracion_enlace(tmp_path: Path) -> None:
    archivado = tmp_path / "archivo.txt"
    archivado.touch()
    origen = tmp_path / "origen.txt"
    try:
        origen.symlink_to(archivado)
    except OSError:
        pytest.skip("Enlaces simbólicos no disponibles")
    registrar(tmp_path, origen, archivado)
    with pytest.raises(PapeleraError, match="enlace simbólico"):
        deshacer_operacion(tmp_path / "papelera", carpeta_base=tmp_path)
    assert archivado.exists()
