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
from limpiador.secretos import MASCARA


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

    monkeypatch.setattr("limpiador.acciones.Motor.ejecutar", explosion)
    monkeypatch.setenv("LIMPIADOR_IA_KEY", clave)

    config = _config_que_falla_con_la_key(clave)
    ruta = escribir_config(tmp_path, config)
    carpeta = tmp_path / "pruebas"
    carpeta.mkdir()
    (carpeta / "foto.png").write_bytes(b"x")

    runner.invoke(
        app,
        ["--config", str(ruta), "ejecutar", "rompe-con-key", str(carpeta), "--simular"],
    )
    resultado = runner.invoke(
        app,
        ["--config", str(ruta), "ejecutar", "rompe-con-key", str(carpeta), "--si"],
    )
    assert resultado.exit_code == 1
    salida = salida_normalizada(resultado.output)
    assert clave not in salida  # la clave NUNCA sale a consola…
    assert MASCARA in salida  # …y sí sale la máscara en su sitio
