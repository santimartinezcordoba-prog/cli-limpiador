#!/usr/bin/env python3
"""Escáner de secretos para todo el repositorio (Bloque 5, «bloqueo de merge»).

Recorre los FICHEROS VERSIONADOS por git (`git ls-files`) y busca patrones de
API key (`limpiador.secretos.PATRONES_API_KEY`). Si encuentra alguno, sale con
código 1 y lista fichero y línea: es el job `secret-scan` de CI, que falla el
PR y bloquea el merge si se cuela una clave.

Reglas:
- NO lee `.env` (que es precisamente donde SÍ puede haber una clave real):
  el escáner audita lo que se commitea, no lo que se queda en tu máquina.
- Tolera placeholders de ejemplo (`TU_API_KEY`, `[REDACTADO]`, docs que
  hablan de claves) vía `_PERMITIDO_ESCANER`.

Uso: `python scripts/escaner_secretos.py` (o `uv run python scripts/...`).
Este fichero no es un test de pytest pese al nombre del job; la comprobación
pytest vive en `tests/test_secretos.py::test_no_hay_claves_en_repo`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete.
RAIZ_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_REPO / "src"))

from limpiador.secretos import contiene_secreto  # noqa: E402

# Marcadores de fichero que se auditan a sí mismo (código y tests del
# escáner/redactor): contienen strings que PARECEN claves pero son fixtures
# sin valor. En lugar de vaciar los patrones globales (debilitar el escáner),
# se exonera exactamente estos ficheros y el resto del repo se escanea con
# todo el rigor. Un fichero exonerado aparece igualmente en `--informativo`.
FICHEROS_EXONERADOS: frozenset[str] = frozenset(
    {"tests/test_secretos.py", "src/limpiador/secretos.py", "scripts/escaner_secretos.py"}
)


def ficheros_versionados(raiz: Path = RAIZ_REPO) -> list[Path]:
    """Ficheros trackeados por git (nunca `.env`: no está versionado)."""
    salida = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=raiz,
        capture_output=True,
        check=True,
        text=True,
    )
    return [raiz / parte for parte in salida.stdout.split("\0") if parte]


def escanear(
    raiz: Path = RAIZ_REPO, exonerar: bool = True
) -> list[str]:
    """Lista `ruta:línea: pista` por cada posible fuga encontrada.

    Con `exonerar=False` se escanea TODO, incluidos los ficheros del propio
    escáner: así `test_no_hay_claves_en_repo` puede auditar TAMBIÉN al audit
    (sus fixtures son seguras por construcción, no por excepción).
    """
    hallazgos: list[str] = []
    from limpiador.secretos import redact

    for fichero in ficheros_versionados(raiz):
        if not fichero.is_file():  # symlink roto o borrado del índice
            continue
        relativa = fichero.relative_to(raiz)
        if exonerar and str(relativa) in FICHEROS_EXONERADOS:
            continue
        try:
            lineas = fichero.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for numero, linea in enumerate(lineas, start=1):
            if contiene_secreto(linea):
                # La pista se redacta: el propio escáner no puede filtrar en
                # su propio log la línea que acabou de detectar. La máscara
                # se corta a 80 caracteres solo para la consola.
                pista = redact(linea).strip()
                hallazgos.append(f"{relativa}:{numero}: {pista[:80]}")
    return hallazgos


def main() -> int:
    """Exit 0 = repo limpio; exit 1 = posible clave versionada (bloquea CI)."""
    hallazgos = escanear()
    if hallazgos:
        print("POSIBLES SECRETOS EN FICHEROS VERSIONADOS:")
        for hallazgo in hallazgos:
            print(f"  ✗ {hallazgo}")
        return 1
    print("Escáner de secretos: ningún patrón de API key en ficheros versionados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
