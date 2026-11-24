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
- La simulación no modifica los archivos de trabajo (probado con hash),
  y la ejecución exige simulación previa y confirmación; «borrar» puede ir a una **papelera reversible**
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

# Simular: muestra qué haría sin modificar los archivos de trabajo
limpiador ejecutar mover-imagenes ~/pruebas-tareas --simular

# Ejecutar de verdad sin preguntar (para scripts; usa antes --simular)
limpiador ejecutar mover-imagenes ~/pruebas-tareas --si

# Deshacer: revierte la última ejecución real (1 = última, 2 = penúltima…)
limpiador deshacer --carpeta ~/pruebas-tareas
limpiador deshacer 2 --carpeta ~/pruebas-tareas

# Smoke test de la IA del centro (exit: 0 ok, 3 sin key, 4 sin red)
limpiador comprobar-ia
limpiador comprobar-ia --json

# Usar otro fichero de acciones (opción global --config)
limpiador --config ./acciones-personales.json listar ./pruebas
limpiador --config ./acciones-personales.json ejecutar borrar-cachés ~/pruebas-tareas --simular
```

### Reglas de seguridad de `ejecutar`

Crea primero la carpeta con `mkdir -p ~/pruebas-tareas` y coloca ahí los
archivos de prueba. Tanto `ejecutar` como `deshacer` solo aceptan esa carpeta
o subcarpetas dentro de ella; las rutas se resuelven antes de comprobar el
límite. `listar` sigue siendo una operación de lectura.

Antes de cada ejecución real hay que simular la misma acción sobre la misma
carpeta. La CLI guarda un comprobante de un solo uso en
`~/.cache/limpiador/simulaciones`, fuera de la carpeta de trabajo. Si cambia
el contenido de la carpeta o la configuración de la acción, hay que volver a
simular. También hay que repetirla si se cancela la confirmación. En acciones
IA, la salida final depende del modelo y el plan mostrado es orientativo.
`--si` constituye la confirmación explícita para scripts, incluso al borrar.

| Flags                 | Comportamiento                                                    |
| --------------------- | ----------------------------------------------------------------- |
| `--simular`           | Muestra el plan y no modifica la carpeta de trabajo (exit `0`).        |
| `--si`                | Confirma la ejecución para scripts, después de simular.                             |
| (ninguno) con terminal | Pide confirmación `s/N`. Si respondes `n`, no hace nada.         |
| (ninguno) sin TTY     | **Se niega a ejecutar y sale con código 2** (evita sorpresas en cron/pipes). |

Además: las acciones solo actúan sobre la carpeta indicada (nivel superior,
no recursivo), rechazan patrones y destinos con `..` (path traversal), ignoran
enlaces simbólicos y nunca sobrescriben ficheros (añaden sufijos `-1`, `-2`…).

### Papelera y `deshacer` (borrado reversible)

Por ejemplo, se puede añadir una acción `borrar` con papelera:

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
| `3`    | `acciones.json` inválido (con `validar --json`, errores estructurados). Con `comprobar-ia`: key ausente. |
| `4`    | Completado en modo degradado (`EXIT_OFFLINE`): acción IA resuelta con heurística local, o `comprobar-ia` sin red. |

### IA (`resumir-texto` y `clasificar-ficheros`)

Desde la v1.2.0 el motor conoce dos acciones IA propias (whitelist ampliada;
el resto de reglas —carpeta objetivo, sin `..`, sin sobrescribir— siguen
vigentes) y el vocabulario completo documentado en la skill
[`docs/skills/acciones-json.md`](docs/skills/acciones-json.md)
(`resumir`, `renombrar-ia`, `clasificar-ia`; hoy implementados
`resumir-texto` y `clasificar-ficheros`):

- **`resumir-texto`**: lee los `.md`/`.txt` que casen con `patrones` y escribe
  el resumen (del centro o de la heurística) en `<nombre>.resumen.md` junto al
  original. `--simular` no modifica los archivos de trabajo.
- **`clasificar-ficheros`**: copia cada fichero a una subcarpeta según su
  tema (respuesta del centro, o extensión/palabras clave si degrada). El
  fichero original permanece en su ubicación.

Campos nuevos en el JSON: `modelo` (obligatorio en acciones IA; si falta,
`validar` sale 3 con `'modelo' es obligatorio…`), `prompt` (opcional) y
`modo_offline` (`heuristica`, por defecto → degrada con exit 4; `estricto` →
sin red la acción falla con exit 1 en lugar de degradar).

**La API KEY nunca se hardcodea ni se commitea**: va en `.env` (ya ignorado) o
en el entorno. Variables reconocidas: `LIMPIADOR_IA_KEY` (obligatoria para la
vía online), `LIMPIADOR_IA_URL`, `LIMPIADOR_IA_MODELO` y `LIMPIADOR_CA_BUNDLE`
(el centro usa certificado auto-firmado: se pasa la ruta del CA en lugar de
desactivar la verificación TLS).

```ini
# .env (ignoradísimo por git; jamás lo comitees)
LIMPIADOR_IA_KEY=sk-…
LIMPIADOR_IA_URL=https://tu-centro/llmapi/v1
LIMPIADOR_IA_MODELO=Qwen38-DualSpark-low
```

**Sin dejar a nadie tirado sin red**: si falta la key o falla la conexión
(timeout, 503, error de red), la acción NO peta — aplica heurística local
(resumen = primeras N frases + longitud; clasificación = por
extensión/palabras clave), muestra el aviso `[modo offline]` y termina con
exit `4`. La heurística es determinista: sin red, `limpiador` sigue siendo
útil y reproducible.

**Sin filtrar la clave**: todo lo que se imprime o se loguea pasa por
`limpiador.secretos.redact()`, que enmascara patrones `sk-…`, `Bearer …`,
`Basic …` y la key exacta. El log de auditoría de las acciones IA
(`resumenes/log_ia.md`) también queda redactado, aunque el error original
arrastrara la key. Un test (`test_no_hay_claves_en_repo`) escanea los
ficheros versionados y revienta si aparece cualquier patrón de key, y el job
CI `secret-scan` repite el escaneo en cada PR: si se filtra una key, el merge
queda bloqueado.

### `comprobar-ia` (smoke test del centro)

```bash
limpiador comprobar-ia          # tabla: key presente/ausente, estado, latencia
limpiador comprobar-ia --json   # lo mismo, parseable por scripts/CI
```

Comprueba en tres pasos, **sin imprimir la key jamás** (solo `presente` /
`ausente`): key en el entorno/`.env` → ping mínimo al modelo con timeout →
informe con latencia. Estados: `ok` (exit `0`), `sin_key` (exit `3`) y
`sin_red` (exit `4`, degradado). Es el comando que la CI ejecuta sin key para
verificar que la CLI degrada correctamente ante fallo de IA.

### MCP context7 (apagado por defecto, solo para doc de `httpx`)

`opencode.json` configura el MCP `context7` (`type: remote`) con
`"enabled": false`: **no carga por defecto** ni gasta tokens en cada sesión.
Se enciende puntualmente con `/mcps` → `context7`, SOLO para consultar la
documentación oficial de `httpx`, y se vuelve a apagar. Es una ayuda de
desarrollo, **no una dependencia runtime** de `limpiador` (ADR-0002).

Auditoría que hizo (con el MCP encendido, contra la doc oficial de httpx):
`httpx.Client(proxies={...})` fue deprecated en 0.26 y está **eliminado** en
0.28 (`TypeError: unexpected keyword argument 'proxies'`); la forma viva es
`proxy=` / `mounts=`. Además, `verify=False` es válido sintácticamente pero
inseguro: la forma correcta es `verify=<ruta-al-CA>`. El código de red de
`limpiador` usa la forma auditada (`base_url` + `httpx.Timeout` +
`follow_redirects` + CA bundle) y el test
`test_forma_obsoleta_proxies_falla` fija en ejecución que reintroducir
`proxies=` rompe: si alguien vuelve a ponerla, la suite lo detecta.


### Seguridad: amenazas y mitigaciones

| Amenaza | Mitigación | Test que lo prueba |
| ------- | ---------- | ------------------ |
| Borrado sorpresa por un patrón mal escrito | `--simular` obligatorio + confirmación `s/N`; sin TTY, exit 2 y nada se ejecuta | `test_simular_no_toca_disco_hash_identico`, `test_sin_tty_y_sin_si_se_niega_y_sale_2` |
| Error humano ya ejecutado | Papelera + manifiesto reversible + `deshacer` (nunca sobrescribe: `.restaurado`) | `test_papelera_borrar_mueve_en_vez_de_borrar`, `test_deshacer_restaura_ruta_original`, `test_deshacer_no_sobrescribe_si_existe` |
| Operaciones arbitrarias (chmod, exec…) | Whitelist pydantic: `mover`, `borrar`, `renombrar`, `dedup` + `resumir-texto`/`clasificar-ficheros`; todo lo demás falla la validación con exit 3 | `test_validar_operacion_no_soportada`, `test_validar_camino_feliz_ia` |
| Path traversal / escapar de la carpeta (`../`, absolutas, `~`, enlaces) | `es_ruta_segura` en patrones/destinos/papelera + contención con `resolve()`; enlaces simbólicos se ignoran | `test_patron_con_path_traversal`, `test_destino_con_path_traversal`, `test_papelera_path_traversal_se_rechaza`, `test_no_sigue_enlaces_simbolicos_fuera_de_la_carpeta` |
| Sobrescribir datos existentes | Colisiones → sufijos `-1`, `-2`…; al deshacer → `.restaurado` y aviso | `test_deshacer_no_sobrescribe_si_existe` |
| Ficheros fuera de la carpeta objetivo | Planificación y ejecución rechazan cualquier ruta que, tras `resolve()`, quede fuera | `test_no_sigue_enlaces_simbolicos_fuera_de_la_carpeta` |
| Filtración de la API key (logs, errores, salida, repo) | `redact()` enmascara `sk-…`/`Bearer …`/key exacta antes de imprimir o loguear; `.env` ignorado; escáner en test y CI | `test_no_hay_claves_en_repo`, `test_redacta_clave_en_error`, `test_error_de_centro_sale_redactado`, `test_sin_key_es_sin_red_error_inmediato`, `test_accion_ia_offline_log_sin_clave`, `test_comprobar_ia_sin_key_texto_sin_clave` |
| IA indisponible (sin key / sin red / centro caído) | Degradación a heurística local determinista con aviso `[modo offline]` y exit 4; `estricto` no degrada; `comprobar-ia` lo diagnostica | `test_comprobar_ia_sin_key`, `test_comprobar_ia_sin_red`, `test_accion_ia_resumir_modo_offline`, `test_accion_ia_clasificar_modo_offline`, `test_accion_ia_estricto_falla_sin_degradar` |
| API obsoleta de httpx (rotura silenciosa al subir 0.28) | Cliente migrado a `base_url`+`httpx.Timeout`+`follow_redirects`+CA bundle; el test ejecuta la forma muerta y aserta el `TypeError` | `test_forma_obsoleta_proxies_falla` |

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
| `test_validar_operacion_no_soportada` | exit 3 + `acciones[1].operacion: valor no soportado (permitido: mover, borrar, renombrar, dedup, resumir-texto, clasificar-ficheros)` | La whitelist se aplica al validar, con índice y campo exactos. |
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
| `test_comprobar_ia_sin_key` | Sin `LIMPIADOR_IA_KEY`: exit 3, estado `sin_key`, key `ausente` y la salida NO contiene `sk-` | Diagnóstico honesto sin red ni credenciales; garantiza cero filtraciones en el mensaje de error. |
| `test_comprobar_ia_sin_red` | Con `ConnectError` parcheado: exit 4 (degradado) y estado `sin_red` | Distingue «falta la key» de «no hay conexión» con códigos distintos; nada cuelga la CLI (timeout corto). |
| `test_comprobar_ia_ok` | Con cliente mock: exit 0, estado `ok` y latencia numérica | El camino feliz del smoke funciona: no todo es degradación. |
| `test_accion_ia_resumir_modo_offline` | Sin red: `resumir-texto` termina con exit 4, escribe `<nombre>.resumen.md` heurístico y avisa `[modo offline]` | «Sin dejar a nadie tirado sin red»: la acción produce resultado útil aunque el centro esté caído. |
| `test_accion_ia_clasificar_modo_offline` | Sin red: `clasificar-ficheros` termina con exit 4 y crea subcarpetas por extensión/palabras clave | La heurística de clasificación es determinista y respeta la contención en la carpeta objetivo. |
| `test_accion_ia_offline_log_sin_clave` | El error simulado LLEVA la key incrustada; ni la salida ni `resumenes/log_ia.md` la contienen | Prueba la redacción justo donde más duele: el log de auditoría de una degradación. |
| `test_accion_ia_estricto_falla_sin_degradar` | `modo_offline: "estricto"` sin red: exit 1 y NADA escrito | Quien exige IA real no obtiene heurística disfrazada: la política se respeta al pie de la letra. |
| `test_accion_ia_camino_feliz_con_mock` | Con cliente mock: exit 0, resumen del «centro» escrito y log redactado | La vía online funciona end-to-end sin tocar la red (mock, no llamadas reales). |
| `test_validar_accion_ia_sin_modelo` | Acción IA sin `modelo`: exit 3 con el campo exacto (`acciones[i]: 'modelo' es obligatorio…`) | Una acción IA sin modelo es una promesa vacía: se detecta al validar, no al ejecutar. |
| `test_validar_modo_offline_invalido` | `modo_offline: "magia"`: exit 3 listando los valores permitidos (`heuristica`, `estricto`) | La política de degradación no se escribe a ojo: la whitelist también protege la config. |
| `test_simular_accion_ia_no_escribe_nada` | `--simular` sobre acción IA: hash del árbol idéntico | La promesa de `--simular` (cero bytes escritos) aplica también a las acciones nuevas. |
| `test_no_hay_claves_en_repo` | Escanea TODOS los ficheros versionados (nunca `.env`) con patrones de key: falla si aparece alguna | «Ninguna clave en el historial» como test, no como promesa: un `sk-…` en un PR rompe la suite y el CI. |
| `test_redacta_clave_en_error` | Un error que contiene la key (una fake) sale enmascarada (`sk-****`) | La redacción funciona con la key real, no solo con patrones genéricos. |
| `test_forma_obsoleta_proxies_falla` | `httpx.Client(proxies={...})` lanza `TypeError` en 0.28; `proxy=`/`mounts=` son la forma viva | Fija en ejecución la auditoría del MCP context7: si alguien reintroduce la API muerta, la suite lo detecta. |

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
      "nombre": "archivar-imagenes-duplicadas",
      "descripcion": "Conserva una imagen de cada contenido y archiva duplicados",
      "operacion": "dedup",
      "patrones": ["*.png", "*.jpg", "*.jpeg", "*.webp"],
      "papelera": true
    },
    {
      "nombre": "renombrar-viejos",
      "descripcion": "Añade el sufijo -revisar a los .txt",
      "operacion": "renombrar",
      "patrones": ["*.txt"],
      "sufijo": "revisar"
    },
    {
      "nombre": "resumir-apuntes",
      "descripcion": "Resume los apuntes .md/.txt con la IA del centro (offline: heurística)",
      "operacion": "resumir-texto",
      "patrones": ["*.md", "*.txt"],
      "modelo": "Qwen38-DualSpark-low",
      "modo_offline": "heuristica"
    },
    {
      "nombre": "clasificar-carpeta",
      "descripcion": "Clasifica por contenido en codigo/, datos/, apuntes/, informes/",
      "operacion": "clasificar-ficheros",
      "patrones": ["*"],
      "modelo": "Qwen38-DualSpark-low",
      "modo_offline": "estricto"
    }
  ]
}
```

Campos de cada acción:

| Campo         | Requerida para            | Descripción                                   |
| ------------- | ------------------------- | --------------------------------------------- |
| `nombre`      | todas                     | Identificador único (lo usas en `ejecutar`).  |
| `descripcion` | todas                     | Texto que se muestra en `limpiador acciones`. |
| `operacion`   | todas                     | Whitelist: `mover`, `borrar`, `renombrar`, `dedup`, `resumir-texto` o `clasificar-ficheros`. |
| `patrones`    | todas                     | Comodines tipo `*.png` (solo nombres, sin rutas). |
| `destino`     | `mover`                   | Carpeta relativa dentro de la carpeta objetivo. |
| `sufijo`      | `renombrar`               | Se añade antes de la extensión: `a.txt` → `a-SUFIJO.txt`. |
| `papelera`    | `borrar`/`dedup` (opcional) | `true` → `<carpeta>/papelera`; `"DIR"` → `<carpeta>/DIR`. |
| `modelo`      | IA (obligatorio)          | Modelo del centro; si falta, `validar` sale 3 con el campo exacto. |
| `prompt`      | IA (opcional)             | Instrucción para afinar la tarea; si se omite, la acción usa su prompt por defecto. |
| `modo_offline`| IA (opcional)             | `heuristica` (por defecto, degrada con exit 4) o `estricto` (sin red, falla con exit 1). |

`limpiador validar` te dice **exactamente qué campo falla** (índice y campo
reales, todos de golpe), por ejemplo:

```text
El fichero 'acciones.json' no es válido:
  ✗ acciones[0].nombre: campo requerido
  ✗ acciones[1].operacion: valor no soportado (permitido: mover, borrar, renombrar, dedup, resumir-texto, clasificar-ficheros)
  ✗ acciones[2]: 'destino' es obligatorio cuando operacion='mover'
```

### Uso end-to-end (de cero a deshacer)

```bash
# 1) Prepara la carpeta y copia la configuración del repositorio
mkdir -p ~/pruebas-tareas
cp acciones.json ~/pruebas-tareas/acciones.json
#    Pon imágenes de prueba duplicadas en ~/pruebas-tareas

# 2) validar: la config debe pasar antes de tocar nada (exit 3 si no)
limpiador --config ~/pruebas-tareas/acciones.json validar

# 3) simular sin modificar los archivos de trabajo
limpiador --config ~/pruebas-tareas/acciones.json ejecutar archivar-imagenes-duplicadas ~/pruebas-tareas --simular

# 4) ejecutar: las imágenes duplicadas viajan a la papelera con manifiesto
limpiador --config ~/pruebas-tareas/acciones.json ejecutar archivar-imagenes-duplicadas ~/pruebas-tareas --si

# 5) te has asustado: deshacer devuelve todo a su sitio
limpiador deshacer --carpeta ~/pruebas-tareas
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
`feature/docs-readme-auditoria`. Para la v1.2.0 (semana 3), en orden de merge:
`feature/mcp-context7`, `feature/motor-ia-offline`, `feature/comprobar-ia`,
`feature/secretos-higiene`, `feature/skill-ia`, `feature/adr-0002` y
`feature/docs-ia`.

## Release

1. Actualiza `CHANGELOG.md` (formato [Keep a Changelog](https://keepachangelog.com/))
   con la versión y fecha.
2. Cambia `version` en `pyproject.toml`.
3. Etiqueta y publica:

```bash
git checkout main && git pull
git tag v1.2.0
git push origin v1.2.0
gh release create v1.2.0 --title "limpiador v1.2.0" --notes-file CHANGELOG.md
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
