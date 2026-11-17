"""Tests del módulo de redacción de secretos (Bloque 5, unidad).

Usan SOLO claves de ejemplo FAKES. La clave real del centro jamás aparece
aquí: de hecho, este fichero lo escanea `test_no_hay_claves_en_repo`.
"""

from __future__ import annotations

from limpiador.secretos import MASCARA, contiene_secreto, redact

# Claves inventadas, formato realista pero sin valor alguno.
FAKE_KEY = "sk-fake000000000000000000"
FAKE_TOKEN = "abcdef0123456789"


def test_redacta_clave_con_prefijo_sk() -> None:
    """Aserta que una clave `sk-...` queda enmascarada.

    Importa porque el requisito 'sin filtrar la clave' exige que cualquier
    `sk-...` que se cuele en un mensaje salga ya redactado antes de imprimir.
    """
    salida = redact(f"el error menciona la clave {FAKE_KEY} otra vez")
    assert FAKE_KEY not in salida
    assert MASCARA in salida


def test_redacta_bearer_y_basic() -> None:
    """Aserta que encabezados `Bearer`/`Basic` se enmascaran completos.

    Importa porque httpx puede reenviar el `Authorization` en un traceback.
    """
    assert FAKE_KEY not in redact(f"Authorization: Bearer {FAKE_KEY}")
    assert redact("Authorization: Bearer xyzabcdef123456") == MASCARA
    assert redact("Authorization: Basic dXNlcjpwYXNzd29yZA==") == MASCARA


def test_redacta_asignacion_json() -> None:
    """Aserta que `"api_key": "..."` (con y sin espacios) se enmascara.

    Importa porque un volcado de config o un JSON de error lleva la clave así.
    """
    assert "supersecreto" not in redact('"api_key": "supersecreto999"')
    assert FAKE_TOKEN not in redact(f"'token': '{FAKE_TOKEN}'")


def test_redacta_secreto_literal_conocido() -> None:
    """Aserta que una clave concreta (sin prefijo reconocible) se oculta.

    Importa porque `redact(texto, secretos=(key,))` protege contra claves que
    no siguen el patrón `sk-`: se sustituyen por coincidencia exacta.
    """
    rara = "Kl4v3-r4r4-sin-patr0n"
    assert rara not in redact(f"aparece {rara} aqui", secretos=(rara,))


def test_redact_deja_texto_normal() -> None:
    """Aserta que un texto sin secretos sale intacto (no sobre-redacta).

    Importa porque redactar en toda la salida no debe romper mensajes legítimos
    como rutas o números: si algo no es secreto, no se toca.
    """
    normal = "movido foto.png -> imagenes/foto.png (2 filas)"
    assert redact(normal) == normal


def test_redact_es_idempotente() -> None:
    """Aserta que redactar dos veces no cambia el resultado.

    Importa porque la misma cadena puede pasar por `redact` en más de un punto
    (error -> log -> consola); no debe degradarse ni corromperse.
    """
    una = redact(f"clave {FAKE_KEY}")
    assert redact(una) == una


def test_contiene_secreto_detecta_y_tolera() -> None:
    """Aserta que el detector cazó claves pero ignora placeholders de ejemplo.

    Importa porque el mismo detector alimenta el escáner del repo: debe fallar
    ante una clave real y NO ante un texto que hable de claves (`TU_API_KEY`).
    """
    assert contiene_secreto(f"token = {FAKE_KEY}")
    assert contiene_secreto('  "api_key": "abcd1234efgh5678"')
    assert not contiene_secreto('apiKey = "TU_API_KEY_AQUI"  # ejemplo')
    assert not contiene_secreto("limpiador listar ./pruebas")
