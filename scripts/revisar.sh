#!/usr/bin/env bash
set -euo pipefail

# Nombre solicitado en la sesión 4; conserva la implementación ya comprobada.
exec bash "$(dirname "$0")/revision_ia.sh" "$@"
