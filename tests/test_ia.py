"""Tests del motor IA, `comprobar-ia` y la auditoría httpx 0.28 (semana 3).

REGLA DE ORO ampliada (Bloque 9): los tests de IA usan SIEMPRE mock o
monkeypatch (`CentroIA._nuevo_cliente` + `ClienteSimulado`); NUNCA hacen una
petición real, ni siquiera con la key de ejemplo. Todo ocurre en `tmp_path`.

Claves: todas las cadenas tipo key de este fichero son FAKES marcadas con
`# scanner: ejemplo`; el escáner del repo (`test_no_hay_claves_en_repo`) lo
verifica y el test `test_redacta_clave_en_error` demuestra que ni esas
acabarían imprimibles.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from conftest import CONFIG_VALIDA, escribir_config, llamar, salida_normalizada
from limpiador import acciones_ia
from limpiador.ia import (
    CentroIA,
    SinRedError,
    fabrica_de_cliente_simulado,
    respuesta_chat,
)
from limpiador.secretos import MASCARA

# Clave de EJEMPLO (inventada, sin valor). Marcada para el escáner.
CLAVE_FALSA = "sk-testfake00000000000000000000"  # scanner: ejemplo


def accion_ia(tmp_path: Path, extra: dict[str, Any]) -> tuple[Path, Path]:
    """Config + carpeta de pruebas con dos textos para las acciones IA."""
    config = json.loads(json.dumps(CONFIG_VALIDA))
    config["acciones"].append(extra)
    ruta = escribir_config(tmp_path, config)
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "apuntes.txt").write_text(
        "Tema 1: la celula. La celula es la unidad de la vida. "
        "El nucleo guarda el ADN. Hay examenes el viernes.",
        encoding="utf-8",
    )
    (carpeta / "script.py").write_text(
        "def main():\n    import sys\n    print('hola')\n", encoding="utf-8"
    )
    return ruta, carpeta


CONFIG_IA_RESUMEN: dict[str, Any] = {
    "nombre": "resumir-notas",
    "descripcion": "Resume los .txt con la IA del centro",
    "operacion": "resumir-texto",
    "patrones": ["*.txt"],
    "modelo": "Qwen38-DualSpark-low",
}

CONFIG_IA_CLASIFICAR: dict[str, Any] = {
    "nombre": "clasificar-textos",
    "descripcion": "Clasifica por contenido en subcarpetas",
    "operacion": "clasificar-ficheros",
    "patrones": ["*.txt", "*.py"],
    "modelo": "Qwen38-DualSpark-low",
}


def inyectar_red(
    monkeypatch: pytest.MonkeyPatch,
    *,
    exc: Exception | None = None,
    respuesta: httpx.Response | None = None,
) -> None:
    """Sustituye el cliente httpx real por el simulado (nunca red real)."""
    monkeypatch.setattr(
        CentroIA, "_nuevo_cliente", fabrica_de_cliente_simulado(exc=exc, respuesta=respuesta)
    )


# --------------------------------------------------------------------------- #
# comprobar-ia (Bloque 4)
# --------------------------------------------------------------------------- #
def test_comprobar_ia_sin_key(runner: CliRunner) -> None:
    """Aserta exit 3 y mensaje «sin key» sin imprimir NUNCA el valor de la key.

    Importa porque el contrato de `comprobar-ia` distingue los tres estados;
    y el modo «sin key» es el único donde el usuario está a salvo por diseño:
    si el mensaje filtrase la variable, se rompería la regla número uno.
    """
    resultado = llamar(runner, ["comprobar-ia", "--json"])
    assert resultado.exit_code == 3
    datos = json.loads(resultado.output)
    assert datos["estado"] == "sin_key"
    assert datos["key"] == "ausente"
    assert CLAVE_FALSA not in resultado.output


def test_comprobar_ia_sin_red(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aserta exit 4 («degradado») simulando fallo de conexión con monkeypatch.

    Importa porque «sin dejar a nadie tirado sin red»: el smoke test debe
    reportar el fallo de red como ESTADO (4), no como crash (1 con traceback),
    y su detalle llega redactado: ni la key fake aparece.
    """
    monkeypatch.setenv("LIMPIADOR_IA_KEY", CLAVE_FALSA)
    inyectar_red(monkeypatch, exc=httpx.ConnectError("sin ruta al host"))
    resultado = llamar(runner, ["comprobar-ia", "--json"])
    assert resultado.exit_code == 4
    datos = json.loads(resultado.output)
    assert datos["estado"] == "sin_red"
    assert datos["key"] == "presente"
    assert CLAVE_FALSA not in resultado.output


def test_comprobar_ia_ok(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aserta exit 0, estado ok y latencia numérica en el camino feliz.

    Importa porque el humo positivo es lo que el usuario ejecuta antes de
    fiarse de las acciones IA; si el ping miente, todo lo demás se apoya en
    una mentira.
    """
    monkeypatch.setenv("LIMPIADOR_IA_KEY", CLAVE_FALSA)
    inyectar_red(monkeypatch, respuesta=respuesta_chat("pong"))
    resultado = llamar(runner, ["comprobar-ia", "--json"])
    assert resultado.exit_code == 0
    datos = json.loads(resultado.output)
    assert datos["estado"] == "ok"
    assert isinstance(datos["latencia_s"], (int, float))


def test_comprobar_ia_sin_key_texto_sin_clave(runner: CliRunner) -> None:
    """Aserta que la salida HUMANA de sin-key tampoco contiene la key.

    Importa porque el requisito dice «sin imprimirla, solo presente/ausente»:
    también aplica al modo texto, no solo al JSON.
    """
    resultado = llamar(runner, ["comprobar-ia"])
    assert resultado.exit_code == 3
    salida = salida_normalizada(resultado.output)
    assert "sin key" in salida
    assert "ausente" in salida
    assert CLAVE_FALSA not in salida


# --------------------------------------------------------------------------- #
# Acciones IA en modo offline (Bloque 3)
# --------------------------------------------------------------------------- #
def test_accion_ia_resumir_modo_offline(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aserta que SIN red la acción termina con exit 4 y escribe un resumen
    heurístico (primeras frases + conteos) — no peta ni deja salida vacía.

    Importa porque «sin dejar a nadie tirado sin red»: el usuario sin key o
    con el centro caído obtiene resultado y aviso, no un traceback.
    """
    monkeypatch.setenv("LIMPIADOR_IA_KEY", CLAVE_FALSA)
    inyectar_red(monkeypatch, exc=httpx.ConnectTimeout("el centro no contesta"))
    ruta, carpeta = accion_ia(tmp_path, CONFIG_IA_RESUMEN)
    resultado = llamar(runner, ["ejecutar", "resumir-notas", str(carpeta), "--si"], config=ruta)
    assert resultado.exit_code == 4
    assert "modo offline" in salida_normalizada(resultado.output)
    resumen = (carpeta / "resumenes" / "resumen-apuntes.md").read_text(encoding="utf-8")
    assert "heurística" in resumen or "Resumen" in resumen
    assert "celula" in resumen  # las primeras frases llegan al resumen
    assert "palabra" in resumen  # nota de longitud incluida


def test_accion_ia_clasificar_modo_offline(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aserta exit 4 + subcarpetas heurísticas correctas sin conexión.

    Importa porque la clasificación offline debe ser útil: `.py` a `codigo/`
    y los apuntes a `apuntes/` por contenido/extensión; si la heurística
    fallara, la acción no sería «degradada», sería «inútil».
    """
    monkeypatch.delenv("LIMPIADOR_IA_KEY", raising=False)  # ni siquiera key
    ruta, carpeta = accion_ia(tmp_path, CONFIG_IA_CLASIFICAR)
    resultado = llamar(runner, ["ejecutar", "clasificar-textos", str(carpeta), "--si"], config=ruta)
    assert resultado.exit_code == 4
    assert (carpeta / "codigo" / "script.py").exists()
    assert (carpeta / "apuntes" / "apuntes.txt").exists()
    # No destructivo: los originales siguen en su sitio.
    assert (carpeta / "script.py").exists()
    assert "modo offline" in salida_normalizada(resultado.output)


def test_accion_ia_offline_log_sin_clave(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aserta que el log de auditoría NO contiene la key aunque el error la lleve.

    Importa porque el log escribe el MOTIVO del degradado, que puede arrastrar
    cabeceras de autenticación del centro; `redact` lo corta antes del disco.
    """
    monkeypatch.setenv("LIMPIADOR_IA_KEY", CLAVE_FALSA)
    # El motivo simulado arrastra la key (como un error del centro real).
    inyectar_red(
        monkeypatch,
        exc=httpx.ConnectError(f"Authorization: Bearer {CLAVE_FALSA} rechazada"),
    )
    ruta, carpeta = accion_ia(tmp_path, CONFIG_IA_RESUMEN)
    resultado = llamar(runner, ["ejecutar", "resumir-notas", str(carpeta), "--si"], config=ruta)
    assert resultado.exit_code == 4
    assert CLAVE_FALSA not in resultado.output
    log = (carpeta / "resumenes" / "log_ia.md").read_text(encoding="utf-8")
    assert CLAVE_FALSA not in log
    assert MASCARA in log


def test_accion_ia_sin_key_sin_red_local(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aserta que SIN key la acción NI INTENTA la red: degrada a heurística.

    Importa porque «sin key» no es un error de configuración que pete: la
    acción termina (exit 4) y produce salida heurística. Sin key ni se abre
    socket: si se abriera, el test de CI (sin red) colgaría.
    """
    monkeypatch.delenv("LIMPIADOR_IA_KEY", raising=False)
    # Sin inyectar nada: si el motor intentara httpx real, fallaría de otra
    # forma (DNS) o colgaría; aquí exigimos exactamente el camino offline.
    ruta, carpeta = accion_ia(tmp_path, CONFIG_IA_RESUMEN)
    resultado = llamar(runner, ["ejecutar", "resumir-notas", str(carpeta), "--si"], config=ruta)
    assert resultado.exit_code == 4
    assert (carpeta / "resumenes" / "resumen-apuntes.md").exists()


def test_accion_ia_camino_feliz_con_mock(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aserta que CON red simulada (mock, no real) la acción usa el resumen del
    modelo y sale con exit 0.

    Importa porque cubre el camino feliz de la ruta IA: si el fallback
    tapara también el éxito, nunca sabríamos que la integración real funciona.
    """
    monkeypatch.setenv("LIMPIADOR_IA_KEY", CLAVE_FALSA)
    inyectar_red(monkeypatch, respuesta=respuesta_chat("La célula es la unidad de la vida."))
    ruta, carpeta = accion_ia(tmp_path, CONFIG_IA_RESUMEN)
    resultado = llamar(runner, ["ejecutar", "resumir-notas", str(carpeta), "--si"], config=ruta)
    assert resultado.exit_code == 0
    resumen = (carpeta / "resumenes" / "resumen-apuntes.md").read_text(encoding="utf-8")
    assert "célula" in resumen
    assert "IA del centro" in resumen


def test_accion_ia_estricto_falla_sin_degradar(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aserta que `modo_offline: "estricto"` NO degrada: sale 1 con el motivo.

    Importa porque el usuario debe poder elegir «IA real o nada» (p. ej. un
    trabajo donde la heurística no vale); el error sale redactado igual.
    """
    monkeypatch.setenv("LIMPIADOR_IA_KEY", CLAVE_FALSA)
    inyectar_red(monkeypatch, exc=httpx.ConnectError("centro caído"))
    config = dict(CONFIG_IA_RESUMEN)
    config["modo_offline"] = "estricto"
    ruta, carpeta = accion_ia(tmp_path, config)
    resultado = llamar(runner, ["ejecutar", "resumir-notas", str(carpeta), "--si"], config=ruta)
    assert resultado.exit_code == 1
    assert "centro caído" in salida_normalizada(resultado.output)
    assert not (carpeta / "resumenes").exists()  # en estricto no escribe


# --------------------------------------------------------------------------- #
# Validación de acciones IA (Bloque 8: caso feo del campo exacto)
# --------------------------------------------------------------------------- #
def test_validar_accion_ia_sin_modelo(runner: CliRunner, tmp_path: Path) -> None:
    """Aserta exit 3 + `modelo` es obligatorio con el campo exacto (nivel objeto).

    Importa porque una acción IA sin modelo es una petición sin destino: la
    rúbrica de validar promete «campo exacto que falla», y aquí se cumple con
    el mismo formato que el resto de incoherencias.
    """
    config = json.loads(json.dumps(CONFIG_VALIDA))
    config["acciones"].append(
        {
            "nombre": "resumir-sin-modelo",
            "descripcion": "IA sin modelo",
            "operacion": "resumir-texto",
            "patrones": ["*.txt"],
        }
    )
    ruta = escribir_config(tmp_path, config)
    resultado = llamar(runner, ["validar"], config=ruta)
    assert resultado.exit_code == 3
    assert (
        "acciones[4]: 'modelo' es obligatorio cuando operacion='resumir-texto'"
        in salida_normalizada(resultado.output)
    )


def test_validar_modo_offline_invalido(runner: CliRunner, tmp_path: Path) -> None:
    """Aserta exit 3 + valores permitidos de `modo_offline` (heuristica/estricto).

    Importa porque el campo controla la degradación: un typo («estricto» mal
    escrito) no puede activar «modo estricto» silencioso ni viceversa.
    """
    config = json.loads(json.dumps(CONFIG_VALIDA))
    config["acciones"].append(
        {
            "nombre": "resumir-mal-modo",
            "descripcion": "modo mal escrito",
            "operacion": "resumir-texto",
            "patrones": ["*.txt"],
            "modelo": "M",
            "modo_offline": "como-pueda",
        }
    )
    ruta = escribir_config(tmp_path, config)
    resultado = llamar(runner, ["validar"], config=ruta)
    assert resultado.exit_code == 3
    assert (
        "acciones[4].modo_offline: valor no soportado (permitido: estricto, heuristica)"
        in salida_normalizada(resultado.output)
    )


def test_validar_camino_feliz_ia(runner: CliRunner, tmp_path: Path) -> None:
    """Aserta que una config con acciones IA válidas pasa `validar` (exit 0).

    Importa porque el camino feliz no puede dar falsos negativos: si la
    whitelist y los campos IA se aceptan, el usuario puede usarlos.
    """
    config = json.loads(json.dumps(CONFIG_VALIDA))
    config["acciones"].append(CONFIG_IA_RESUMEN)
    ruta = escribir_config(tmp_path, config)
    resultado = llamar(runner, ["validar"], config=ruta)
    assert resultado.exit_code == 0


def test_listar_y_acciones_incluyen_ia(runner: CliRunner, tmp_path: Path) -> None:
    """Aserta que `acciones` muestra la nueva operación IA (descubribilidad).

    Importa porque una función que no aparece en `limpiador acciones` no
    existe para el usuario.
    """
    config = json.loads(json.dumps(CONFIG_VALIDA))
    config["acciones"].append(CONFIG_IA_CLASIFICAR)
    ruta = escribir_config(tmp_path, config)
    resultado = llamar(runner, ["acciones"], config=ruta)
    assert resultado.exit_code == 0
    assert "clasificar-textos" in resultado.output
    assert "clasificar-ficheros" in resultado.output


def test_simular_accion_ia_no_escribe_nada(runner: CliRunner, tmp_path: Path) -> None:
    """Aserta que `--simular` de una acción IA no escribe NADA en el disco.

    Importa porque la promesa de `--simular` (probada con hash para las
    operaciones de fichero) debe extenderse a las IA: plan sin efectos.
    """
    from conftest import tree_hash

    config = json.loads(json.dumps(CONFIG_VALIDA))
    config["acciones"].append(CONFIG_IA_RESUMEN)
    ruta = escribir_config(tmp_path, config)
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "nota.txt").write_text("una frase. otra frase.", encoding="utf-8")
    antes = tree_hash(carpeta)
    resultado = llamar(
        runner, ["ejecutar", "resumir-notas", str(carpeta), "--simular"], config=ruta
    )
    assert resultado.exit_code == 0
    assert tree_hash(carpeta) == antes


# --------------------------------------------------------------------------- #
# Unitarias de la heurística offline (motor, sin CLI ni red)
# --------------------------------------------------------------------------- #
def test_resumen_heuristico_determinista() -> None:
    """Aserta que el resumen offline coge las primeras frases y nota longitud.

    Importa porque es el «plan B» que ve el usuario sin red: debe ser
    determinista y útil (primeras N frases + métricas del original).
    """
    texto = "Primera frase. Segunda frase. Tercera frase. Cuarta frase extra."
    resumen = acciones_ia.resumen_heuristico(texto)
    assert "Primera frase. Segunda frase. Tercera frase." in resumen
    assert "Cuarta frase extra." not in resumen
    assert "4 frase(s)" in resumen


def test_clasificar_heuristica_por_contenido_y_extension() -> None:
    """Aserta la heurística: código por palabras, apuntes por contenido, resto
    por extensión, y siempre una etiqueta válida del contrato.

    Importa porque la clasificación offline decide subcarpetas: si devolviera
    etiquetas fuera de la whitelist, escribiría rutas inesperadas.
    """
    assert acciones_ia.clasificar_heuristica("a.py", "def f(): return 1") == "codigo"
    assert (
        acciones_ia.clasificar_heuristica("b.txt", "tema 3: concepto nuevo, examen pronto")
        == "apuntes"
    )
    assert acciones_ia.clasificar_heuristica("c.xyz", "nada que ver") == "sin-clasificar"
    assert acciones_ia.clasificar_heuristica("d.css", "body { }") == "codigo"


def test_etiqueta_desde_respuesta_tolera_ruido() -> None:
    """Aserta que una respuesta IA con texto extra se reduce a etiqueta válida.

    Importa porque los modelos responden con prosa («La categoría es
    código.»); sin normalizar, se crearían carpetas basura.
    """
    assert acciones_ia._etiqueta_desde_respuesta("La categoría es: Código.") == "codigo"
    assert acciones_ia._etiqueta_desde_respuesta("no sé") == "sin-clasificar"


# --------------------------------------------------------------------------- #
# Red unitaria de `CentroIA` (Bloque 3/4: mensaje de SinRedError redactado)
# --------------------------------------------------------------------------- #
def test_error_de_centro_sale_redactado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aserta que el SinRedError que genera el centro lleva la key tapada.

    Importa porque el error viaja a consola Y al log: si httpx reenviara la
    cabecera Authorization en el mensaje, el mensaje ya nace redactado.
    """
    inyectar_red(
        monkeypatch,
        exc=httpx.ConnectError(f"header Authorization: Bearer {CLAVE_FALSA} inválida"),
    )
    centro = CentroIA(
        key=CLAVE_FALSA,
        base_url="https://centro.ies/v1",
        modelo="M",
        timeout=2.0,
    )
    with pytest.raises(SinRedError) as exc_info:
        centro.completar("hola")
    assert CLAVE_FALSA not in str(exc_info.value)
    assert MASCARA in str(exc_info.value)


def test_sin_key_es_sin_red_error_inmediato() -> None:
    """Aserta que sin key `completar` lanza SinRedError sin tocar httpx.

    Importa porque la degradación empieza en la PRESENCIA de la key: ni se
    construye el cliente (ni se fuga nada por un intento de conexión).
    """
    centro = CentroIA(key=None, base_url="https://x", modelo="M", timeout=1.0)
    with pytest.raises(SinRedError):
        centro.completar("hola")


# --------------------------------------------------------------------------- #
# Auditoría httpx 0.28 (Bloque 1: la forma obsoleta NO puede volver)
# --------------------------------------------------------------------------- #
def test_forma_obsoleta_proxies_falla() -> None:
    """Aserta que `httpx.Client(proxies=...)` es TypeError en 0.28.

    Importa porque fija en EJECUCIÓN la obsolescencia que detectó el MCP:
    `proxies=` (heredada de requests, deprecated en 0.26) está ELIMINADA en
    0.28 — la forma viva es `proxy=`/`mounts=`. Si alguien reintrodujera la
    forma muerta «por costumbre», este test lo documenta y el código de
    `ia.py` (probado por el resto de la suite) no la usa.
    """
    with pytest.raises(TypeError):
        httpx.Client(proxies={"https://": "http://proxy:3128"})  # type: ignore[call-arg]
    # Y la forma correcta (la que usa CentroIA) no lanza nada:
    with httpx.Client(
        base_url="https://centro.ies/v1",
        timeout=httpx.Timeout(1.0),
        proxy="http://proxy:3128",
    ) as cliente:
        assert isinstance(cliente, httpx.Client)


def test_carga_dotenv_no_pisa_el_entorno(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aserta que el `.env` se carga sin pisar variables ya definidas y que
    una clave del `.env` llega a `leer_key` (la key vive SOLO ahí).

    Importa porque el contrato de seguridad dice: key en `.env` (ignorado) o
    entorno — este test es la única vez que una key «vive» en disco, dentro
    de tmp_path y con valor falso.
    """
    from limpiador.config import cargar_dotenv
    from limpiador.ia import leer_key

    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f'# comentario\nLIMPIADOR_IA_KEY="{CLAVE_FALSA}"\nOTRA=42\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMPIADOR_IA_URL", "https://previo.ies/v1")
    assert cargar_dotenv(dotenv) == dotenv
    assert leer_key() == CLAVE_FALSA  # la key del .env llega al motor
    assert leer_key.__name__ == "leer_key"
    # no pisa lo ya definido:
    assert cargar_dotenv(dotenv) == dotenv
