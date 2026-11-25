"""Regresiones de la interfaz y de respuestas de IA, sin conexiones reales."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import httpx
import pytest
import typer
from typer.testing import CliRunner

from conftest import llamar, salida_normalizada
from limpiador import acciones_ia, cli
from limpiador.acciones import Motor, Operacion
from limpiador.config import Accion
from limpiador.errores import AccionError
from limpiador.ia import (
    CentroIA,
    SinRedError,
    fabrica_de_cliente_simulado,
    httpx_client_apto_auditoria,
    respuesta_chat,
)
from limpiador.secretos import redact
from limpiador.tabla import tabla_operaciones


@pytest.mark.parametrize("comando", ["acciones", "ejecutar"])
def test_cli_config_invalida(
    runner: CliRunner, tmp_path: Path, comando: str,
) -> None:
    ruta = tmp_path / "rota.json"
    ruta.write_text("{}", encoding="utf-8")
    args = [comando] if comando == "acciones" else [comando, "x", str(tmp_path)]
    resultado = llamar(runner, args, config=ruta)
    assert resultado.exit_code == 3
    assert "no es válido" in salida_normalizada(resultado.output)


def test_cli_carpeta_es_fichero(runner: CliRunner, tmp_path: Path) -> None:
    fichero = tmp_path / "archivo.txt"
    fichero.touch()
    resultado = llamar(runner, ["listar", str(fichero)])
    assert resultado.exit_code == 1
    assert "no es una carpeta" in salida_normalizada(resultado.output)


@pytest.mark.parametrize("paquete", ["rich", "limpiador"])
def test_doctor_dependencia_ausente(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, paquete: str,
) -> None:
    original = importlib.metadata.version

    def version(nombre: str) -> str:
        if nombre == paquete:
            raise importlib.metadata.PackageNotFoundError(nombre)
        return original(nombre)

    monkeypatch.setattr(importlib.metadata, "version", version)
    resultado = llamar(runner, ["doctor"])
    assert resultado.exit_code == 1
    assert "Entorno no apto" in salida_normalizada(resultado.output)


@pytest.mark.parametrize("fase", ["planificar", "huella_inicial", "huella_final", "ejecutar"])
def test_cli_error_no_modifica(
    runner: CliRunner, config_valida: Path, carpeta_pruebas: Path,
    monkeypatch: pytest.MonkeyPatch, fase: str,
) -> None:
    origen = carpeta_pruebas / "foto.png"
    contenido = origen.read_bytes()

    def fallo(*args: object, **kwargs: object) -> None:
        raise AccionError("fallo controlado")

    if fase in {"planificar", "ejecutar"}:
        monkeypatch.setattr(Motor, fase, fallo)
    else:
        original = cli.huella
        llamadas = 0

        def huella(config: Accion, carpeta: Path) -> str:
            nonlocal llamadas
            llamadas += 1
            if fase == "huella_inicial" or llamadas == 2:
                raise OSError("fallo controlado")
            return original(config, carpeta)

        monkeypatch.setattr(cli, "huella", huella)

    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(carpeta_pruebas), "--si"],
        config=config_valida,
    )
    assert resultado.exit_code == 1
    assert "fallo controlado" in salida_normalizada(resultado.output)
    assert origen.read_bytes() == contenido
    assert not (carpeta_pruebas / "imagenes").exists()


def test_confirmacion_interrumpida(
    runner: CliRunner, config_valida: Path, carpeta_pruebas: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_stdin_interactivo", lambda: True)

    def interrumpir(*args: object, **kwargs: object) -> str:
        raise typer.Abort()

    monkeypatch.setattr(typer, "prompt", interrumpir)
    resultado = llamar(
        runner, ["ejecutar", "borrar-temporales", str(carpeta_pruebas)], config=config_valida,
    )
    assert resultado.exit_code == 2
    assert (carpeta_pruebas / "datos.tmp").exists()


@pytest.mark.parametrize("estado", ["ok", "sin_red"])
def test_comprobar_ia_texto(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, estado: str,
) -> None:
    monkeypatch.setenv("LIMPIADOR_IA_KEY", "valor ficticio")
    fabrica = (
        fabrica_de_cliente_simulado(respuesta=respuesta_chat("hola"))
        if estado == "ok"
        else fabrica_de_cliente_simulado(exc=httpx.ConnectError("sin conexión"))
    )
    monkeypatch.setattr(CentroIA, "_nuevo_cliente", fabrica)
    resultado = llamar(runner, ["comprobar-ia"])
    assert resultado.exit_code == (0 if estado == "ok" else 4)
    assert "valor ficticio" not in resultado.output
    assert ("centro respondió" if estado == "ok" else "sin red") in resultado.output


@pytest.mark.parametrize("datos", [[], {}, {"choices": []}, {"choices": [1]},
                                  {"choices": [{}]}, {"choices": [{"message": 3}]}])
def test_ia_respuestas_invalidas(datos: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        CentroIA, "_nuevo_cliente",
        fabrica_de_cliente_simulado(respuesta=httpx.Response(200, json=datos)),
    )
    centro = CentroIA(key="valor ficticio", base_url="https://centro.ies/v1",
                      modelo="M", timeout=1)
    with pytest.raises(SinRedError, match="respuesta del centro"):
        centro.ping()


def test_ia_respuesta_numerica(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = httpx.Response(200, json={"choices": [{"message": {"content": 42}}]})
    monkeypatch.setattr(CentroIA, "_nuevo_cliente",
                        fabrica_de_cliente_simulado(respuesta=respuesta))
    centro = CentroIA(key="valor ficticio", base_url="https://centro.ies/v1",
                      modelo="M", timeout=1)
    assert centro.ping().contenido == "42"


def test_cliente_httpx_configuracion() -> None:
    with httpx_client_apto_auditoria() as cliente:
        assert cliente.base_url.scheme == "https"
        assert cliente.follow_redirects is False
        assert cliente.timeout.connect == 8.0


def test_lectura_ia_ausente(tmp_path: Path) -> None:
    assert acciones_ia.leer_texto(tmp_path / "ausente.txt") == ""
    assert "sin texto reconocible" in acciones_ia.resumen_heuristico("")


def test_tabla_de_ejecucion_real(tmp_path: Path) -> None:
    tabla = tabla_operaciones([Operacion("borrar", tmp_path / "f.txt")], simulacion=False)
    assert tabla.title == "Pasos a ejecutar"
    assert tabla.row_count == 1


def test_redaccion_cadena_vacia() -> None:
    assert redact("") == ""
