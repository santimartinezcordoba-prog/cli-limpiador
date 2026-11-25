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
git archive HEAD src tests docs scripts .github .opencode .gitignore .env.example \
    LICENSE README.md SPEC.md CHANGELOG.md acciones.json pyproject.toml uv.lock opencode.json |
    tar -xf - -C "$revision"

cd "$revision"
echo "Iniciando revisión del proyecto..."
opencode run --agent revision-segura "Revisa los archivos de este proyecto limpiador.
Comprueba estructura, seguridad y pruebas. Indica errores concretos con archivo y línea.
Limítate a leer esta copia; no leas archivos externos, .env ni credenciales.
No ejecutes comandos, no modifiques archivos ni consultes servicios externos.
La copia no contiene historial Git ni archivos locales. No declares fallos de compilación o tests sin haberlos ejecutado; distingue observaciones de hipótesis.
Devuelve un informe breve en español con posibles mejoras."
echo "Revisión finalizada."
