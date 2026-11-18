"""Cliente del centro de IA (OpenAI-compatible) con httpx 0.28 y modo sin red.

Este módulo es la ÚNICA capa que toca la red. El motor de acciones
(`limpiador.acciones_ia`) llama a `CentroIA` y nunca a `httpx` directamente, de
modo que la lógica de negocio se testa sin Typer y sin conexión real.

Forma correcta en httpx 0.28 (auditada con el MCP context7, ver ADR-0.002):
    httpx.Client(base_url=..., timeout=httpx.Timeout(...), follow_redirects=True)

# obsoleto en httpx 0.28: `httpx.Client(proxies={...})` se ELIMINÓ. `proxies`
# (plural, dict) fue marcado deprecated en 0.26 y eliminado en 0.28: ahora da
# `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'`.
# La forma correcta es `proxy=<url-única>` (o `mounts={patrón: client}` para
# proxies por esquema). Aquí no usamos proxy; si alguien necesitara uno, se
# pasaría `proxy=`, jamás `proxies=`.
# obsoleto en httpx 0.28: `httpx.Client(verify=False)` para silenciar el TLS.
# La docencia de auditores del MCP detectó esta forma en el borrador del
# cliente: pasar `verify=False` SIGUE siendo sintaxis válida en 0.28, pero el
# parámetro está documentado como «opt-out inseguro»: desactiva por completo
# la comprobación de certificados (MITM libre). La forma correcta con un CA
# auto-firmado (el del centro) es `verify=<ruta-al-CA>` o un
# `ssl.SSLContext`; `False` solo en tests con transporte simulado. Aquí se
# pasa `verify=LIMPIADOR_CA_BUNDLE` si existe, y `True` en otro caso.

Modo sin red («sin dejar a nadie tirado sin red»): si falta la API key o falla
la conexión (timeout, 503, fallo de red, error de protocolo), `completar` lanza
`SinRedError`. La acción IA lo captura y degrada a heurística local (exit 4).

Redacción: cualquier mensaje de error que generamos pasa por `redact` ANTES de
devolverlo, para que la clave (aunque httpx la reenviara en un traceback) nunca
llegue a la consola ni al log.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import ClassVar, Final

import httpx

from limpiador.config import cargar_dotenv
from limpiador.secretos import redact

# Configuración del centro del IES (no es un secreto: es solo la URL).
BASE_URL_POR_DEFECTO: Final[str] = "https://ia.simarro/llmapi/v1"
MODELO_POR_DEFECTO: Final[str] = "Qwen38-DualSpark-low"

ENV_KEY: Final[str] = "LIMPIADOR_IA_KEY"
ENV_URL: Final[str] = "LIMPIADOR_IA_URL"
ENV_MODELO: Final[str] = "LIMPIADOR_IA_MODELO"
ENV_CA: Final[str] = "LIMPIADOR_CA_BUNDLE"
ENV_TIMEOUT: Final[str] = "LIMPIADOR_IA_TIMEOUT"

# Tiempo máximo (s) de una petición al centro. Corto a propósito: si el centro
# está caído, queremos degradar pronto al modo offline, no colgar la CLI.
TIMEOUT_POR_DEFECTO: Final[float] = 8.0


class SinRedError(Exception):
    """No se pudo hablar con el centro (sin key o fallo de conexión).

    Su mensaje ya está REDACTADO: puede imprimirse o loguearse sin exponer la
    clave. La acción IA lo usa para activar el modo offline.
    """


def leer_key(entorno: Mapping[str, str] | None = None) -> str | None:
    """Devuelve la API key del entorno o None. Nunca la imprime ni la loguea."""
    env = os.environ if entorno is None else entorno
    key = env.get(ENV_KEY, "").strip()
    return key or None


def leer_url(entorno: Mapping[str, str] | None = None) -> str:
    """URL base del centro (por defecto la del IES)."""
    env = os.environ if entorno is None else entorno
    return env.get(ENV_URL, "").strip() or BASE_URL_POR_DEFECTO


def leer_modelo_por_defecto(entorno: Mapping[str, str] | None = None) -> str:
    """Modelo a usar cuando la acción no especifica uno."""
    env = os.environ if entorno is None else entorno
    return env.get(ENV_MODELO, "").strip() or MODELO_POR_DEFECTO


def leer_timeout(entorno: Mapping[str, str] | None = None) -> float:
    """Timeout en segundos; un valor ilegible cae al valor por defecto."""
    env = os.environ if entorno is None else entorno
    crudo = env.get(ENV_TIMEOUT, "").strip()
    try:
        valor = float(crudo)
    except ValueError:
        return TIMEOUT_POR_DEFECTO
    return valor if valor > 0 else TIMEOUT_POR_DEFECTO


@dataclass(frozen=True)
class RespuestaIA:
    """Salida de una llamada al centro: contenido y latencia en segundos."""

    contenido: str
    latencia_s: float


_FabricaCliente = Callable[..., AbstractContextManager[httpx.Client]]


@contextmanager
def _cliente_por_defecto(**kwargs: object) -> Iterator[httpx.Client]:
    """Cliente httpx real (forma correcta 0.28: `base_url`+`timeout`, sin
    `proxies`). Es la implementación por defecto de `CentroIA._nuevo_cliente`;
    los tests la sustituyen para simular timeout/503/fallo de red sin red.
    """
    with httpx.Client(**kwargs) as cliente:  # type: ignore[arg-type]
        yield cliente


def httpx_client_apto_auditoria() -> AbstractContextManager[httpx.Client]:
    """Cliente httpx construido con la forma AUDITADA como correcta en 0.28.

    Lo usa `tests/test_ia_httpx.py::test_forma_obsoleta_proxies_falla`: si
    alguien reintroduce `proxies=` (o `verify=False`) en el código de red,
    ese test lo detecta. Documenta en EJECUCIÓN lo que la docencia oficial
    dice: `proxy=`/`mounts=` son la forma viva; `proxies=` murió en 0.28.
    """
    return _cliente_por_defecto(
        base_url=BASE_URL_POR_DEFECTO,
        timeout=httpx.Timeout(TIMEOUT_POR_DEFECTO),
        follow_redirects=True,
    )


class CentroIA:
    """Fachada mínima sobre la API de chat del centro (OpenAI-compatible)."""

    # Punto de inyección de tests: `monkeypatch.setattr(CentroIA,
    # "_nuevo_cliente", fabrica_falsa)`. En producción es el httpx.Client
    # real; los tests lo sustituyen y NUNCA tocan la red.
    # staticmethod EXPLÍCITO: sin él, `self._nuevo_cliente(...)` reenviaría la
    # instancia como primer argumento posicional.
    _nuevo_cliente: ClassVar[_FabricaCliente] = staticmethod(_cliente_por_defecto)

    def __init__(self, *, key: str | None, base_url: str, modelo: str, timeout: float,
                 ca_bundle: str | None = None) -> None:
        self._key = key
        self._base_url = base_url
        self._modelo = modelo
        self._timeout = timeout
        # `verify` por defecto True (TLS verificado). El centro usa un CA
        # auto-firmado: para hablar con él se pasa la ruta del CA por
        # LIMPIADOR_CA_BUNDLE, en lugar de desactivar la comprobación.
        self._ca_bundle = ca_bundle

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str] | None = None) -> CentroIA:
        """Construye el cliente leyendo toda la configuración del entorno.

        Si no se pasa `entorno` explícito, hidrata antes el `.env` (ignorado
        por git): así la key llega sin hardcodear y sin que nadie recuerde
        exportarla a mano.
        """
        env = os.environ if entorno is None else entorno
        if entorno is None:
            cargar_dotenv()
        return cls(
            key=leer_key(env),
            base_url=leer_url(env),
            modelo=leer_modelo_por_defecto(env),
            timeout=leer_timeout(env),
            ca_bundle=env.get(ENV_CA, "").strip() or None,
        )

    @property
    def tiene_key(self) -> bool:
        return bool(self._key)

    @property
    def modelo(self) -> str:
        """Modelo que se usará cuando la acción no especifica uno."""
        return self._modelo

    def ping(self, mensaje: str = "ping", max_tokens: int = 8) -> RespuestaIA:
        """Petición mínima para el smoke test de `comprobar-ia`."""
        return self.completar(mensaje, max_tokens=max_tokens)

    def completar(
        self,
        instruccion: str,
        *,
        modelo: str | None = None,
        max_tokens: int = 512,
    ) -> RespuestaIA:
        """Devuelve el texto del modelo o lanza `SinRedError` (mensaje redactado).

        «Sin key» y «sin red» se tratan igual: se lanza `SinRedError` para que
        la acción degrade a heurística. Nunca se propaga un `httpx.HTTPError`
        con la cabecera `Authorization` en claro.
        """
        if not self._key:
            raise SinRedError("no hay API key configurada (LIMPIADOR_IA_KEY)")
        modelo_usado = modelo or self._modelo
        inicio = time.monotonic()
        try:
            with self._nuevo_cliente(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=True,
                verify=self._ca_bundle if self._ca_bundle else True,
                headers={"Authorization": f"Bearer {self._key}"},
            ) as cliente:
                respuesta = cliente.post(
                    "/chat/completions",
                    json={
                        "model": modelo_usado,
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": instruccion}],
                    },
                )
                respuesta.raise_for_status()
                datos = respuesta.json()
        except httpx.TimeoutException as exc:
            raise SinRedError(
                redact(f"timeout al contactar el centro ({self._timeout}s): {exc}")
            ) from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            raise SinRedError(
                redact(f"el centro respondió HTTP {code} al pedir '{modelo_usado}'")
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            # RequestError: fallo de red/DNS/TLS. ValueError: cuerpo no-JSON.
            raise SinRedError(
                redact(f"sin conexión con el centro: {type(exc).__name__}: {exc}")
            ) from exc
        latencia = time.monotonic() - inicio
        contenido = _extraer_contenido(datos)
        return RespuestaIA(contenido=contenido, latencia_s=latencia)


def _extraer_contenido(datos: object) -> str:
    """Extrae `choices[0].message.content` con tolerancia a formas raras."""
    if not isinstance(datos, dict):
        raise SinRedError("respuesta del centro sin estructura esperada")
    choices = datos.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SinRedError("respuesta del centro sin 'choices'")
    primero = choices[0]
    if not isinstance(primero, dict):
        raise SinRedError("respuesta del centro mal formada")
    mensaje = primero.get("message")
    if not isinstance(mensaje, dict):
        raise SinRedError("respuesta del centro sin 'message'")
    contenido = mensaje.get("content", "")
    return contenido if isinstance(contenido, str) else str(contenido)


# --------------------------------------------------------------------------- #
# Comprobación de la IA (`limpiador comprobar-ia`).
# --------------------------------------------------------------------------- #
# Estados de la comprobación. Se serializan tal cual con `--json`, así que el
# contrato de parseo es estable: "ok" | "sin_key" | "sin_red".
COMPROBACION_OK: Final[str] = "ok"
COMPROBACION_SIN_KEY: Final[str] = "sin_key"
COMPROBACION_SIN_RED: Final[str] = "sin_red"


@dataclass(frozen=True)
class ComprobacionIA:
    """Resultado del smoke test del centro para `comprobar-ia`."""

    estado: str
    latencia_s: float | None = None
    detalle: str = ""
    modelo: str = ""
    tiene_key: bool = False


def comprobar_centro(centro: CentroIA) -> ComprobacionIA:
    """Smoke test: key presente (sin imprimirla) + ping mínimo con timeout.

    Nunca menciona la clave: `detalle` sale ya redactado. «Sin key» y «sin
    red» se distinguen solo por la presencia de la variable de entorno, no
    por el contenido de ningún mensaje.
    """
    if not centro.tiene_key:
        return ComprobacionIA(
            estado=COMPROBACION_SIN_KEY,
            detalle="falta la variable de entorno LIMPIADOR_IA_KEY (o .env)",
            modelo=centro.modelo,
            tiene_key=False,
        )
    try:
        respuesta = centro.ping()
    except SinRedError as exc:
        return ComprobacionIA(
            estado=COMPROBACION_SIN_RED,
            detalle=redact(str(exc)),
            modelo=centro.modelo,
            tiene_key=True,
        )
    return ComprobacionIA(
        estado=COMPROBACION_OK,
        latencia_s=respuesta.latencia_s,
        detalle="respuesta del centro recibida",
        modelo=centro.modelo,
        tiene_key=True,
    )
