# limpiador 🧹

[![CI](https://github.com/santimartinezcordoba-prog/cli-limpiador/actions/workflows/ci.yml/badge.svg)](https://github.com/santimartinezcordoba-prog/cli-limpiador/actions/workflows/ci.yml)
![cobertura](https://img.shields.io/badge/cobertura-80%25_gate-green)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![Release](https://img.shields.io/github/v/release/santimartinezcordoba-prog/cli-limpiador)

CLI en Python para **limpiar y ordenar ficheros** de forma declarativa:
defines qué hacer en un fichero JSON (`acciones.json`) y la herramienta lo
ejecuta, con simulación previa y confirmaciones de seguridad.

- Órdenes: `version`, `doctor`, `listar`, `acciones`, `validar` (`--json`),
  `ejecutar` (`--simular` / `--si`) y `deshacer`.
- Stack: Python 3.10+, [Typer](https://typer.tiangolo.com/) (CLI),
  [Rich](https://rich.readthedocs.io/) (tablas), [pydantic](https://docs.pydantic.dev/)
  (validación), pytest, ruff, mypy.
- 100 % segura por diseño: `--simular` no toca el disco (probado con hash),
  sin terminal no ejecuta nada, «borrar» puede ir a una **papelera reversible**
  con `deshacer`, las operaciones están en whitelist y todo path traversal
  (`..`) se rechaza.

## Requisitos

- Python **3.10 o superior**.
- [`uv`](https://docs.astral.sh/uv/) **o** [`pipx`](https://pipx.pypa.io/)
  para instalarla como comando global.

## Instalación (una sola orden)

Con **uv**:

```bash
uv tool install git+https://github.com/santimartinezcordoba-prog/cli-limpiador.git
```

Con **pipx**:

```bash
pipx install git+https://github.com/santimartinezcordoba-prog/cli-limpiador.git
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

# Validar la configuración (exit code 3 si es inválida; lista TODOS los errores)
limpiador validar
limpiador validar --json   # lo mismo, como JSON estructurado para scripts

# Diagnóstico del entorno (Python + dependencias): sale 0 si todo vale
limpiador doctor

# Simular: muestra qué haría, sin tocar nada
limpiador ejecutar mover-imagenes ./pruebas --simular

# Ejecutar de verdad sin preguntar (para scripts; usa antes --simular)
limpiador ejecutar mover-imagenes ./pruebas --si

# Deshacer: revierte la última ejecución real (1 = última, 2 = penúltima…)
limpiador deshacer
limpiador deshacer 2

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

### Papelera y `deshacer` (borrado reversible)

Una acción `borrar` o `dedup` puede activar la papelera:

```json
{ "nombre": "borrar-temporales", "operacion": "borrar", "patrones": ["*.tmp"], "papelera": true }
```

- `"papelera": true` → los ficheros se **mueven** a `<carpeta>/papelera/<YYYYMMDD-HHMMSS>/`
  en vez de destruirse. `"papelera": "DIR"` usa `<carpeta>/DIR` (ruta relativa segura).
- Cada ejecución real (`--si`) escribe un **manifiesto** en
  `<papelera>/.manifiesto/<op-id>.json` con `op_id`, `timestamp`, `accion`,
  `carpeta_base` y la lista `{origen, destino}` de cada fichero.
- `limpiador deshacer [N]` lee el manifiesto más reciente (o el N-ésimo) y
  devuelve cada fichero a su ruta original. Si el original ya existe, **no
  sobrescribe**: crea `nombre.restaurado.ext` y avisa. Sin manifiesto o con
  borrados definitivos (sin papelera): sale con código 1 explicándolo.

Por qué esto hace «seguro» un borrado: mover es atómico y no destruye el
contenido; el manifiesto convierte la papelera en un historial reversible.
`borrar` sin papelera sigue existiendo, pero es el único caso no reversible
(`deshacer` lo detecta y se niega).

### Códigos de salida

| Código | Significado                                                   |
| ------ | ------------------------------------------------------------- |
| `0`    | Correcto (incluye simulación, cancelación voluntaria y `deshacer` OK). |
| `1`    | Acción/carpeta inexistente, fallo al ejecutar, o `deshacer` sin manifiesto / operación no reversible. |
| `2`    | Falta confirmación (sin TTY y sin `--si`) o flags incompatibles. |
| `3`    | `acciones.json` inválido (con `validar --json`, errores estructurados). |

### Seguridad: amenazas y mitigaciones

| Amenaza | Mitigación | Test que lo prueba |
| ------- | ---------- | ------------------ |
| Borrado sorpresa por un patrón mal escrito | `--simular` obligatorio por cultura + confirmación `s/N`; sin TTY, exit 2 y nada se ejecuta | `test_simular_no_toca_disco_hash_identico`, `test_sin_tty_y_sin_si_se_niega_y_sale_2` |
| Error humano ya ejecutado | Papelera + manifiesto reversible + `deshacer` (nunca sobrescribe: `.restaurado`) | `test_papelera_borrar_mueve_en_vez_de_borrar`, `test_deshacer_restaura_ruta_original`, `test_deshacer_no_sobrescribe_si_existe` |
| Operaciones arbitrarias (chmod, exec…) | Whitelist pydantic: solo `mover`, `borrar`, `renombrar`, `dedup`; todo lo demás falla la validación con exit 3 | `test_validar_operacion_no_soportada` |
| Path traversal / escapar de la carpeta (`../`, absolutas, `~`, enlaces) | `es_ruta_segura` en patrones/destinos/papelera + contención con `resolve()`; enlaces simbólicos se ignoran | `test_patron_con_path_traversal`, `test_destino_con_path_traversal`, `test_papelera_path_traversal_se_rechaza`, `test_no_sigue_enlaces_simbolicos_fuera_de_la_carpeta` |
| Sobrescribir datos existentes | Colisiones → sufijos `-1`, `-2`…; al deshacer → `.restaurado` y aviso | `test_deshacer_no_sobrescribe_si_existe` |
| Ficheros fuera de la carpeta objetivo | Planificación y ejecución rechazan cualquier ruta que, tras `resolve()`, quede fuera | `test_no_sigue_enlaces_simbolicos_fuera_de_la_carpeta` |

### Auditoría de tests

Cada fila dice qué comprueba un test y por qué ese test importa. Si alguna
aserción fallara, la garantía correspondiente deja de ser cierta.

| Test | Qué aserta | Por qué importa |
| ---- | ---------- | --------------- |
| `test_ayuda_enumera_todas_las_ordenes` | `--help` sale 0 y lista `version`, `listar`, `acciones`, `validar`, `ejecutar`, `deshacer`, `doctor` y `--config` | Sin ayuda completa nadie descubre la CLI; evita que un refactor «pierda» una orden. |
| `test_version_muestra_la_version_instalada` | `version` imprime la versión del paquete instalado (metadatos) | Prueba de humo de instalación: lo instalado coincide con `pyproject.toml`. |
| `test_listar_muestra_nombre_tipo_tamano_y_fecha` | La tabla tiene las 4 columnas y los ficheros de `tmp_path` | Contrato de salida legible de `listar`. |
| `test_listar_no_modifica_nada` | Instantánea byte-a-byte idéntica tras listar | `listar` es solo lectura: no puede haber efectos secundarios. |
| `test_acciones_lista_todas_las_acciones_con_descripcion` | `acciones` imprime los 3 nombres del JSON y su descripción | El usuario ve lo que puede ejecutar antes de ejecutar nada. |
| `test_validar_ok` | JSON correcto → salida 0 y «válido» | El camino feliz no puede dar falsos negativos. |
| `test_validar_json_mal_formado` | JSON corrupto → exit 3 + «JSON inválido» con línea y columna | Un typo en el JSON debe detectarse, no ejecutarse «a medias». |
| `test_validar_operacion_no_soportada` | exit 3 + `acciones[1].operacion: valor no soportado (permitido: mover, borrar, renombrar, dedup)` | La whitelist se aplica al validar, con índice y campo exactos. |
| `test_validar_mover_sin_destino` | exit 3 + `acciones[0].destino: campo requerido ('destino' es obligatorio cuando operacion='mover')` | Coherencia entre campos: un `mover` sin destino es una bomba de relojería. |
| `test_validar_json_flag_con_errores` | `--json` devuelve TODOS los errores como array y sale 3 | Auditoría automatizable: un script puede exigir `valido: true`. |
| `test_simular_no_toca_disco_hash_identico` (parametrizado por operación) | SHA256 del árbol (rutas+contenidos) idéntico antes/después de `--simular` + «simulación»/«no se ha modificado» en la salida | Prueba empírica estrella: `--simular` no escribe ni un byte. |
| `test_si_mueve_las_imagenes_de_verdad` | `--si` mueve `foto.png`/`selfie.jpg` a `imagenes/` conservando el contenido | La ejecución real hace exactamente lo prometido en el plan. |
| `test_sin_tty_y_sin_si_se_niega_y_sale_2` | Sin terminal y sin `--si`: exit 2, pide `--si` y no mueve nada | En cron/CI/pipes no puede haber destrucción silenciosa. |
| `test_carpeta_inexistente_al_ejecutar` | `ejecutar` sobre carpeta que no existe → exit 1 + «no existe» | Caso feo: la ruta objetivo también se valida, no solo la acción. |
| `test_papelera_borrar_mueve_en_vez_de_borrar` | Con `papelera: true`, el `.tmp` aparece en `papelera/<ts>/` y se escribe el manifiesto | «Borrar» seguro = mover + mapa reversible. |
| `test_deshacer_restaura_ruta_original` | Tras `--si` + `deshacer`, el fichero vuelve con su contenido | El botón de deshacer funciona de verdad. |
| `test_deshacer_no_sobrescribe_si_existe` | El original nuevo queda intacto; lo recuperado acaba en `.restaurado` + AVISO | Deshacer nunca puede destruir datos posteriores. |
| `test_deshacer_sin_manifiesto_sale_1` | Sin papelera → exit 1 con mensaje claro | El contrato de exit codes también es seguridad. |
| `test_papelera_path_traversal_se_rechazada`* | `papelera: "../huida"` → exit 3 (campo exacto) | La papelera tampoco puede escribir fuera de la carpeta. |
| `test_dedup_mueve_duplicados_a_papelera_y_deshacer_restaura` | Dedup SHA256 deja uno, archiva el duplicado y `deshacer` lo devuelve | La operación nueva también nace reversible. |
| `test_accion_inexistente_muestra_error_y_alternativas` | exit 1 + lista de acciones válidas | Los errores enseñan a usar la herramienta. |

\* En el código: `test_papelera_path_traversal_se_rechaza`.

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
      "descripcion": "Borra ficheros temporales .tmp (a la papelera: reversible)",
      "operacion": "borrar",
      "patrones": ["*.tmp"],
      "papelera": true
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
| `operacion`   | todas                     | Whitelist: `mover`, `borrar`, `renombrar` o `dedup`. |
| `patrones`    | todas                     | Comodines tipo `*.png` (solo nombres, sin rutas). |
| `destino`     | `mover`                   | Carpeta relativa dentro de la carpeta objetivo. |
| `sufijo`      | `renombrar`               | Se añade antes de la extensión: `a.txt` → `a-SUFIJO.txt`. |
| `papelera`    | `borrar`/`dedup` (opcional) | `true` → `<carpeta>/papelera`; `"DIR"` → `<carpeta>/DIR`. |

`limpiador validar` te dice **exactamente qué campo falla** (índice y campo
reales, todos de golpe), por ejemplo:

```text
El fichero 'acciones.json' no es válido:
  ✗ acciones[0].nombre: campo requerido
  ✗ acciones[1].operacion: valor no soportado (permitido: mover, borrar, renombrar, dedup)
  ✗ acciones[2]: 'destino' es obligatorio cuando operacion='mover'
```

### Uso end-to-end (de cero a deshacer)

```bash
# 1) "init": copia el ejemplo del repo y activa la papelera en el borrado
cp acciones.json ./mi-carpura/acciones.json
#    (en "borrar-temporales" ya viene "papelera": true de serie)

# 2) validar: la config debe pasar antes de tocar nada (exit 3 si no)
limpiador --config ./mi-carpura/acciones.json validar

# 3) simular: tabla de pasos SIN tocar el disco
limpiador --config ./mi-carpura/acciones.json ejecutar borrar-temporales ./mi-carpura --simular

# 4) ejecutar de verdad: los .tmp viajan a papelera/<marca>/ + manifiesto
limpiador --config ./mi-carpura/acciones.json ejecutar borrar-temporales ./mi-carpura --si

# 5) te has asustado: deshacer devuelve todo a su sitio
cd ./mi-carpura && limpiador deshacer
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

## Cómo contribuir (ramas y PRs)

Cada funcionalidad entra a `main` desde su rama, con commits convencionales
(`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`) y un PR cuyo checklist
exige: **tests en verde · README actualizado · caso feo cubierto**:

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
`feature/github-actions`, `feature/release-v1` y, para la v1.1.0:
`feature/validar-pydantic`, `feature/papelera-deshacer`,
`feature/test-hash-simular`, `feature/ci-instalacion-limpia`,
`feature/docs-auditoria` y, para la v1.1.1: `feature/validar-mensajes-exactos`,
`feature/cobertura-pytest`, `feature/ci-lint-test-smoke` y
`feature/docs-readme-auditoria`.

## Release

1. Actualiza `CHANGELOG.md` (formato [Keep a Changelog](https://keepachangelog.com/))
   con la versión y fecha.
2. Cambia `version` en `pyproject.toml`.
3. Etiqueta y publica:

```bash
git checkout main && git pull
git tag v1.1.1
git push origin v1.1.1
gh release create v1.1.1 --title "limpiador v1.1.1" --notes-file CHANGELOG.md
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
