# limpiador 🧹

CLI en Python para **limpiar y ordenar ficheros** de forma declarativa:
defines qué hacer en un fichero JSON (`acciones.json`) y la herramienta lo
ejecuta, con simulación previa y confirmaciones de seguridad.

- Órdenes: `version`, `listar`, `acciones`, `validar`, `ejecutar`.
- Stack: Python 3.10+, [Typer](https://typer.tiangolo.com/) (CLI),
  [Rich](https://rich.readthedocs.io/) (tablas), pytest, ruff, mypy.
- 100 % segura por diseño: `--simular` no toca el disco, sin terminal no
  ejecuta nada, no sigue enlaces simbólicos y no escribe fuera de la carpeta
  objetivo.

## Requisitos

- Python **3.10 o superior**.
- [`uv`](https://docs.astral.sh/uv/) **o** [`pipx`](https://pipx.pypa.io/)
  para instalarla como comando global.

## Instalación (una sola orden)

Con **uv**:

```bash
uv tool install git+https://github.com/TU_USUARIO/cli-limpiador.git
```

Con **pipx**:

```bash
pipx install git+https://github.com/TU_USUARIO/cli-limpiador.git
```

Después la CLI queda disponible globalmente como `limpiador`:

```bash
limpiador --help
limpiador version
```

> Para probarla desde una copia local del repositorio:
> `uv tool install .` o `pipx install .` (dentro de la carpeta del repo).

## Uso

```bash
# Ayuda general con todas las órdenes
limpiador --help

# Versión instalada
limpiador version

# Tabla con nombre, tipo, tamaño y fecha de cada fichero (no modifica nada)
limpiador listar                # carpeta actual
limpiador listar ./pruebas

# Acciones definidas en ./acciones.json
limpiador acciones

# Validar la configuración (exit code 3 si es inválida)
limpiador validar

# Simular: muestra qué haría, sin tocar nada
limpiador ejecutar mover-imagenes ./pruebas --simular

# Ejecutar de verdad sin preguntar (para scripts; usa antes --simular)
limpiador ejecutar mover-imagenes ./pruebas --si

# Usar otro fichero de acciones (opción global --config)
limpiador --config ./acciones-personales.json listar ./pruebas
limpiador --config ./acciones-personales.json ejecutar borrar-cachés ./pruebas --simular
```

### Reglas de seguridad de `ejecutar`

| Flags                 | Comportamiento                                                    |
| --------------------- | ----------------------------------------------------------------- |
| `--simular`           | Muestra la tabla de pasos y **no toca el disco** (exit `0`).        |
| `--si`                | Ejecuta sin preguntar (para scripts).                             |
| (ninguno) con terminal | Pide confirmación `s/N`. Si respondes `n`, no hace nada.         |
| (ninguno) sin TTY     | **Se niega a ejecutar y sale con código 2** (evita sorpresas en cron/pipes). |

Además: las acciones solo actúan sobre la carpeta indicada (nivel superior,
no recursivo), rechazan patrones y destinos con `..` (path traversal), ignoran
enlaces simbólicos y nunca sobrescriben ficheros (añaden sufijos `-1`, `-2`…).

### Códigos de salida

| Código | Significado                                                   |
| ------ | ------------------------------------------------------------- |
| `0`    | Correcto (incluye simulación y cancelación voluntaria).       |
| `1`    | Acción inexistente, carpeta inexistente o fallo al ejecutar.  |
| `2`    | Falta confirmación (sin TTY y sin `--si`) o flags incompatibles. |
| `3`    | `acciones.json` inválido.                                     |

### Ejemplo de salida (`listar`)

```text
Contenido de ./pruebas
┏━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Nombre      ┃ Tipo    ┃   Tamaño ┃ Modificado       ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ datos.tmp   │ fichero │    150 B │ 2026-11-02 18:09 │
│ foto.png    │ fichero │  19.5 KB │ 2026-11-02 18:09 │
│ informe.pdf │ fichero │ 390.6 KB │ 2026-11-02 18:09 │
│ readme.txt  │ fichero │     11 B │ 2026-11-02 18:09 │
└─────────────┴─────────┴──────────┴──────────────────┘
```

## Crear tu `acciones.json`

Copia el [`acciones.json`](acciones.json) de ejemplo del repositorio y
adáptalo. Estructura:

```json
{
  "version": 1,
  "acciones": [
    {
      "nombre": "mover-imagenes",
      "descripcion": "Mueve imágenes a una carpeta imagenes/",
      "operacion": "mover",
      "patrones": ["*.png", "*.jpg", "*.jpeg", "*.webp"],
      "destino": "imagenes"
    },
    {
      "nombre": "borrar-temporales",
      "descripcion": "Borra ficheros temporales .tmp",
      "operacion": "borrar",
      "patrones": ["*.tmp"]
    },
    {
      "nombre": "renombrar-viejos",
      "descripcion": "Añade el sufijo -revisar a los .txt",
      "operacion": "renombrar",
      "patrones": ["*.txt"],
      "sufijo": "revisar"
    }
  ]
}
```

Campos de cada acción:

| Campo         | Requerida para            | Descripción                                   |
| ------------- | ------------------------- | --------------------------------------------- |
| `nombre`      | todas                     | Identificador único (lo usas en `ejecutar`).  |
| `descripcion` | todas                     | Texto que se muestra en `limpiador acciones`. |
| `operacion`   | todas                     | `mover`, `borrar` o `renombrar`.              |
| `patrones`    | todas                     | Comodines tipo `*.png` (solo nombres, sin rutas). |
| `destino`     | `mover`                   | Carpeta relativa dentro de la carpeta objetivo. |
| `sufijo`      | `renombrar`               | Se añade antes de la extensión: `a.txt` → `a-SUFIJO.txt`. |

`limpiador validar` te dice **exactamente qué campo falla**, por ejemplo:

```text
El fichero 'acciones.json' no es válido:
  ✗ acciones[0].nombre: campo requerido
  ✗ acciones[1].operacion: valor no soportado
  ✗ acciones[2].destino: debe ser una ruta relativa segura
```

## Ejecutar las pruebas

El repositorio usa `pytest` y **todas las pruebas trabajan sobre carpetas
temporales** (`tmp_path`); nunca tocan ficheros reales.

Con uv:

```bash
uv run pytest        # pruebas
uv run ruff check    # linting
uv run mypy          # tipos
```

Con pip/venv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest && ruff check && mypy
```

## Proceso de desarrollo (ramas y PRs)

Cada funcionalidad entra a `main` desde su rama con commits convencionales:

```bash
git checkout -b feature/listar        # 1. rama por funcionalidad
# ...cambios...                        # 2. commit convencional
git commit -m "feat: orden listar con tabla Rich"
git push -u origin feature/listar     # 3. PR
gh pr create --fill --base main
gh pr merge --squash                  # 4. merge a main (CI en verde)
```

Ramas usadas: `feature/estructura-base`, `feature/cli-typer`,
`feature/listar`, `feature/validar`, `feature/ejecutar`, `feature/pruebas`,
`feature/github-actions`, `feature/release-v1`.

## Release

1. Actualiza `CHANGELOG.md` (formato [Keep a Changelog](https://keepachangelog.com/))
   con la versión y fecha.
2. Cambia `version` en `pyproject.toml`.
3. Etiqueta y publica:

```bash
git checkout main && git pull
git tag v1.0
git push origin v1.0
gh release create v1.0 --title "limpiador v1.0" --notes-file CHANGELOG.md
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
