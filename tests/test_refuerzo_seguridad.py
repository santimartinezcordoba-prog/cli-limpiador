"""Regresiones de seguridad con red simulada y archivos temporales."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from conftest import llamar
from limpiador.ia import (
    CentroIA,
    SinRedError,
    fabrica_de_cliente_simulado,
    leer_timeout,
)
from limpiador.secretos import MASCARA


@pytest.mark.parametrize("url", [
    "http://centro.ies/v1",
    "https://",
    "ftp://centro.ies/v1",
    "https://usuario:pass@centro.ies/v1",
])
def test_rechaza_url_insegura(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def prohibido(**kwargs: object) -> httpx.Client:
        pytest.fail("No debe construirse el cliente")

    monkeypatch.setattr(CentroIA, "_nuevo_cliente", prohibido)
    centro = CentroIA(key="valor ficticio", base_url=url, modelo="M", timeout=1)
    with pytest.raises(SinRedError, match="HTTPS"):
        centro.completar("ping")


@pytest.mark.parametrize("valor", ["nan", "inf", "-inf", "-1", "0", "texto", ""])
def test_timeout_invalido(valor: str) -> None:
    assert leer_timeout({"LIMPIADOR_IA_TIMEOUT": valor}) == 8.0


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_redaccion_literal_sin_prefijo(
    error: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    clave = "valorFicticioSinPrefijo"
    monkeypatch.setattr(
        CentroIA, "_nuevo_cliente",
        fabrica_de_cliente_simulado(exc=error(f"error de prueba {clave}")),
    )
    centro = CentroIA(key=clave, base_url="https://centro.ies/v1", modelo="M", timeout=1)
    with pytest.raises(SinRedError) as exc:
        centro.completar("ping")
    assert clave not in str(exc.value)
    assert MASCARA in str(exc.value)


def test_redirect_no_se_sigue(monkeypatch: pytest.MonkeyPatch) -> None:
    visitas: list[str] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        visitas.append(str(peticion.url))
        return httpx.Response(307, headers={"Location": "https://otro.ies/"})

    def cliente(**kwargs: object) -> httpx.Client:
        assert kwargs["follow_redirects"] is False
        return httpx.Client(
            transport=httpx.MockTransport(responder), **kwargs  # type: ignore[arg-type]
        )

    monkeypatch.setattr(CentroIA, "_nuevo_cliente", cliente)
    centro = CentroIA(
        key="valor ficticio", base_url="https://centro.ies/v1", modelo="M", timeout=1
    )
    with pytest.raises(SinRedError, match="307"):
        centro.completar("ping")
    assert visitas == ["https://centro.ies/v1/chat/completions"]


def test_ca_inexistente_degrada(tmp_path: Path) -> None:
    centro = CentroIA(
        key="valor ficticio", base_url="https://centro.ies/v1", modelo="M",
        timeout=1, ca_bundle=str(tmp_path / "no-existe.pem"),
    )
    with pytest.raises(SinRedError, match="sin conexión"):
        centro.completar("ping")


def _manifiesto(raiz: Path, base: Path, entradas: list[dict[str, str]]) -> Path:
    ruta = raiz / "papelera" / ".manifiesto" / "prueba.json"
    ruta.parent.mkdir(parents=True)
    ruta.write_text(json.dumps({
        "op_id": "prueba", "timestamp": "2026-11-25T10:00:00",
        "accion": "prueba", "operacion": "mover", "carpeta_base": str(base),
        "entradas": entradas, "deshecha": None,
    }), encoding="utf-8")
    return ruta


def test_manifiesto_raiz_manipulada(runner: CliRunner, tmp_path: Path) -> None:
    raiz = tmp_path / "autorizada"
    otra = tmp_path / "otra"
    otra.mkdir()
    archivo = otra / "archivo.txt"
    archivo.write_text("intacto", encoding="utf-8")
    ruta = _manifiesto(raiz, otra, [
        {"origen": str(otra / "nuevo.txt"), "destino": str(archivo)},
    ])
    antes = ruta.read_bytes()
    resultado = llamar(runner, ["deshacer", "--carpeta", str(raiz)])
    assert resultado.exit_code == 1
    assert archivo.read_text(encoding="utf-8") == "intacto"
    assert not (otra / "nuevo.txt").exists()
    assert ruta.read_bytes() == antes


def test_manifiesto_valida_todo_antes_de_mover(runner: CliRunner, tmp_path: Path) -> None:
    raiz = tmp_path / "autorizada"
    raiz.mkdir()
    archivo = raiz / "archivo.txt"
    archivo.write_text("intacto", encoding="utf-8")
    fuera = tmp_path / "fuera.txt"
    fuera.write_text("intacto", encoding="utf-8")
    _manifiesto(raiz, raiz, [
        {"origen": str(tmp_path / "nuevo.txt"), "destino": str(fuera)},
        {"origen": str(raiz / "nuevo.txt"), "destino": str(archivo)},
    ])
    resultado = llamar(runner, ["deshacer", "--carpeta", str(raiz)])
    assert resultado.exit_code == 1
    assert archivo.exists() and fuera.exists()
    assert not (raiz / "nuevo.txt").exists()


@pytest.mark.parametrize("parte", ["papelera", ".manifiesto"])
def test_papelera_enlazada(runner: CliRunner, tmp_path: Path, parte: str) -> None:
    raiz = tmp_path / "autorizada"
    raiz.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    enlace = raiz / "papelera"
    if parte == ".manifiesto":
        enlace.mkdir()
        enlace = enlace / parte
    try:
        enlace.symlink_to(fuera, target_is_directory=True)
    except OSError:
        pytest.skip("El sistema no permite crear enlaces simbólicos")
    resultado = llamar(runner, ["deshacer", "--carpeta", str(raiz)])
    assert resultado.exit_code == 1
    assert not list(fuera.iterdir())
