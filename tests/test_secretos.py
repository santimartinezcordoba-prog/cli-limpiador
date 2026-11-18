"""Tests del módulo de redacción de secretos (Bloque 5, unidad).

Usan SOLO claves de ejemplo FAKES. La clave real del centro jamás aparece
aquí: de hecho, este fichero lo escanea `test_no_hay_claves_en_repo`.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from conftest import CONFIG_VALIDA, escribir_config, salida_normalizada
from limpiador.acciones import AccionError
from limpiador.cli import app
from limpiador.secretos import MASCARA, contiene_secreto, redact


def _config_que_falla_con_la_key(clave: str) -> dict[str, Any]:
    """Config con una acción cuyo fallo arrastra la key (motor parcheado abajo).

    El fallo se simula parcheando `acciones.ejecutar` (ver fixture del test),
    no llamando a ninguna IA: el punto es PROBAR LA REDACCIÓN de la salida,
    no la conexión.
    """
    config = copy.deepcopy(CONFIG_VALIDA)
    config["acciones"].append(
        {
            "nombre": "rompe-con-key",
            "descripcion": "acción que falla arrastrando la key",
            "operacion": "mover",
            "patrones": ["*.png"],
            "destino": "x",
        }
    )
    return config

# Claves inventadas, formato realista pero sin valor alguno.
FAKE_KEY = "sk-fake000000000000000000"  # scanner: ejemplo
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
    assert redact("Authorization: Bearer xyzabcdef123456") == MASCARA  # scanner: ejemplo
    assert redact("Authorization: Basic dXNlcjpwYXNzd29yZA==") == MASCARA


def test_redacta_asignacion_json() -> None:
    """Aserta que `"api_key": "..."` (con y sin espacios) se enmascara.

    Importa porque un volcado de config o un JSON de error lleva la clave así.
    """
    assert "supersecreto" not in redact('"api_key": "supersecreto999"')  # scanner: ejemplo
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
    assert contiene_secreto('  "api_key": "abcd1234efgh5678"')  # scanner: ejemplo
    assert not contiene_secreto('apiKey = "TU_API_KEY_AQUI"  # ejemplo')
    assert not contiene_secreto("limpiador listar ./pruebas")


# --------------------------------------------------------------------------- #
# Bloque 5: garantías mecánicas de «ninguna clave en el historial».
# --------------------------------------------------------------------------- #
def test_no_hay_claves_en_repo() -> None:
    """Aserta que NINGÚN fichero versionado del repo contiene un patrón de key.

    Importa porque es la garantía mecánica del requisito «la API KEY nunca
    aparece en el historial git»: si alguien comitea una clave (incluso en
    un README o un test), CI bloquea el merge. Escanea TODO, incluida la
    propia suite de secretos (`exonerar=False`): los fixtures de este
    fichero son falsos por construcción y pasan igualmente.
    """
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(raiz / "scripts"))
    from escaner_secretos import escanear

    hallazgos = escanear(raiz, exonerar=False)
    assert hallazgos == [], "posibles claves versionadas:\n" + "\n".join(hallazgos)


def test_redacta_clave_en_error(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aserta que un error de ejecución que LLEVA la key dentro sale enmascarado.

    Importa porque «sin filtrar la clave» exige cubrir el peor camino: si el
    motor revienta con un mensaje que incrusta el valor de la variable (p. ej.
    el error del centro volcando la cabecera Authorization), la consola solo
    puede ver `[REDACTADO]`. El fallo se SIMULA (monkeypatch del motor, nunca
    red real); lo que se prueba es la REDACCIÓN de la salida.
    """
    clave = "sk-cfake00000000000000000000000"  # scanner: ejemplo

    def explosion(*args: object, **kwargs: object) -> Any:
        # Error que arrastra la key, como haría un traceback con cabeceras.
        raise AccionError(
            f"el centro rechazó la petición: Authorization: Bearer {clave}"
        )

    # La CLI hace `from ... import ejecutar` al importar: se parchea la
    # referencia que usa `cli.py`, que es la que se invoca al ejecutar.
    monkeypatch.setattr("limpiador.cli.ejecutar_plan", explosion)
    monkeypatch.setenv("LIMPIADOR_IA_KEY", clave)

    config = _config_que_falla_con_la_key(clave)
    ruta = escribir_config(tmp_path, config)
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "foto.png").write_bytes(b"x")

    resultado = runner.invoke(
        app,
        ["--config", str(ruta), "ejecutar", "rompe-con-key", str(carpeta), "--si"],
    )
    assert resultado.exit_code == 1
    salida = salida_normalizada(resultado.output)
    assert clave not in salida  # la clave NUNCA sale a consola…
    assert MASCARA in salida  # …y sí sale la máscara en su sitio
