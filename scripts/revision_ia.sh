#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v opencode >/dev/null 2>&1; then
    echo "Error: OpenCode no está instalado." >&2
    exit 1
fi

# Copia únicamente archivos seleccionados del último commit.
# No copia .env, credenciales locales ni cambios sin commit.
revision="$(mktemp -d)"
trap 'rm -rf -- "$revision"' EXIT
git archive HEAD src tests docs README.md SPEC.md acciones.json pyproject.toml opencode.json |
    tar -xf - -C "$revision"

cd "$revision"
echo "Iniciando revisión del proyecto..."
opencode run --agent plan "Revisa los archivos de este proyecto limpiador.
Comprueba estructura, seguridad y pruebas. Indica errores concretos con archivo y línea.
Limítate a leer esta copia; no leas archivos externos, .env ni credenciales.
No ejecutes comandos, no modifiques archivos ni consultes servicios externos.
Devuelve un informe breve en español con posibles mejoras."
echo "Revisión finalizada."
