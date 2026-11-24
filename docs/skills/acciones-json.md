# Skill: formato de `acciones.json` (con operaciones IA)

> Documento para agentes/usuarios que generan o editan el fichero de
> acciones de `limpiador`. Describe el JSON **actual** (v1.2.0): las cuatro
> operaciones clásicas y las cuatro operaciones IA disponibles, cómo se valida cada
> tipo y qué campos son obligatorios. La versión humana de referencia es el
> README del repo; este documento y el README se mantienen coherentes.

## Esqueleto del fichero

```json
{
  "version": 1,
  "acciones": [ { "nombre": "...", "operacion": "...", ... } ]
}
```

- `version`: entero, por defecto `1`.
- `acciones`: lista NO vacía. Cada acción es un objeto; **los campos extra
  se rechazan** (`extra="forbid"`): si inventas uno, `validar` falla con
  `campo no permitido`.
- Reglas universales: `nombre` único (duplicado = error), `descripcion`
  texto, `patrones` lista de comodines de SOLO NOMBRE (`*.png` ✓,
  `sub/*.png` ✗) sin path traversal (`..`, rutas absolutas → exit 3).

## Operaciones y campos por tipo

| Campo           | aplica a                            | notas |
| --------------- | ----------------------------------- | ----- |
| `nombre`        | todas (obligatorio)                 | lo usas en `limpiador ejecutar NOMBRE` |
| `descripcion`   | todas (obligatorio)                 | |
| `operacion`     | todas (obligatorio)                 | whitelist: `mover`, `borrar`, `renombrar`, `dedup`, `resumir-texto`, `clasificar-ficheros`, `preguntas-repaso`, `extraer-tareas` |
| `patrones`      | todas (obligatorio)                 | al menos 1 |
| `destino`       | `mover` (obligatorio)               | carpeta relativa dentro de la carpeta objetivo |
| `sufijo`        | `renombrar` (obligatorio)           | `a.txt` → `a-SUFIJO.txt` |
| `papelera`      | `borrar`/`dedup` (opcional)         | `true` → `<carpeta>/papelera`; `"DIR"` → `<carpeta>/DIR` |
| `modelo`        | **IA (obligatorio)**                | p. ej. `"Qwen38-DualSpark-low"` |
| `prompt`        | IA (opcional)                       | instrucción afinada; sin él, el prompt por defecto |
| `modo_offline`  | IA (opcional)                       | `"heuristica"` (por defecto) o `"estricto"` |

### Cómo se valida cada tipo (errores exactos que produce `validar`)

- Operación fuera de whitelist:
  `acciones[i].operacion: valor no soportado (permitido: mover, borrar, renombrar, dedup, resumir-texto, clasificar-ficheros, preguntas-repaso, extraer-tareas)`.
- Coherencias a nivel de OBJETO (con índice real del array):
  - `acciones[i]: 'destino' es obligatorio cuando operacion='mover'`
  - `acciones[i]: 'sufijo' es obligatorio cuando operacion='renombrar'`
  - `acciones[i]: 'modelo' es obligatorio cuando operacion='resumir-texto'`
    (y análogo para `clasificar-ficheros`)
  - `acciones[i]: 'destino' solo aplica a la operación 'mover'` (también
    para acciones IA; lo mismo se aplica al campo `sufijo`).
  - `acciones[i]: 'modelo'/'prompt' solo aplican a operaciones IA (clasificar-ficheros, extraer-tareas, preguntas-repaso, resumir-texto)`
  - `'papelera' solo aplica a las operaciones 'borrar' o 'dedup'`
- `modo_offline` con valor inválido:
  `acciones[i].modo_offline: valor no soportado (permitido: estricto, heuristica)`.
- Salida: TODOS los errores de golpe + exit `3`.

## Operaciones IA — qué hacen y cómo degradan

Las operaciones IA usan el modelo del centro vía httpx (OpenAI-compatible).
**Sin key o sin red NO petan**: degradan a heurística local, avisan
`[modo offline]` y terminan con **exit code 4** (completado en modo
degradado). Con IA real: exit 0. Con `"modo_offline": "estricto"`: sin red
falla (exit 1) en vez de degradar.

- **`resumir-texto`** — lee los ficheros que casan (`.md`/`.txt`…) y escribe
  en `<carpeta>/resumenes/resumen-<nombre>.md` un resumen del modelo.
  Offline: primeras 3 frases + conteo de frases/palabras/líneas.
- **`clasificar-ficheros`** — copia cada fichero (NO destructivo: el
  original se queda) a una subcarpeta según su CONTENIDO: `codigo/`,
  `datos/`, `apuntes/`, `informes/` o `sin-clasificar/`. Offline: palabras
  clave del contenido y, si nada casa, la extensión.
- **`preguntas-repaso`** — genera preguntas de estudio; sin red propone preguntas
  sencillas desde las primeras frases y señala modo offline.
- **`extraer-tareas`** — extrae tareas; sin red solo detecta líneas marcadas con
  TODO, pendiente, hacer o `[ ]` e indica si no encuentra ninguna.
- **`renombrar-ia`** — TIPO DOCUMENTADO con futuro: propuesta para renombrar
  ficheros con un nombre generado por el modelo (aún NO está en la
  whitelist; si aparece en un JSON, `validar` lo rechaza con «valor no
  soportado»). Se lista aquí para que el agente conozca el vocabulario IA
  completo: `resumir`, `renombrar-ia`, `clasificar-ia` → hoy implementados,
  cuatro operaciones reales: `resumir-texto`, `clasificar-ficheros`,
  `preguntas-repaso` y `extraer-tareas`.

### Seguridad de las acciones IA (obligatorio al escribir configs)

- La API key NUNCA va en `acciones.json` (es JSON versionable): vive en
  `.env` (`LIMPIADOR_IA_KEY=...`) o en el entorno. En el JSON solo se
  referencian `modelo` y `prompt`.
- `prompt` no debe contener secretos ni datos sensibles: viaja al centro y
  puede acabar en logs del centro.
- Toda salida de la CLI (errores, log `resumenes/log_ia.md`) pasa por el
  redactor de secretos: `sk-…`, `Bearer …` o la key literal se enmascaran.

## Ejemplo completo (3 acciones, 2 de ellas IA)

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
      "nombre": "resumir-apuntes",
      "descripcion": "Resume los apuntes .md/.txt con la IA del centro (offline: heurística)",
      "operacion": "resumir-texto",
      "patrones": ["*.md", "*.txt"],
      "modelo": "Qwen38-DualSpark-low",
      "prompt": "Resume en un párrafo breve, en español, indicando las ideas clave.",
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

## Checklist del agente antes de entregar un `acciones.json`

1. `limpiador --config TU_ARCHIVO.json validar` → exit 0 (corrige TODOS los
   errores listados, no solo el primero).
2. Toda acción IA lleva `modelo`.
3. Ninguna key ni secreto en el JSON ni en `prompt`.
4. Ejecuta siempre `ejecutar NOMBRE CARPETA --simular` antes de `--si`.
5. Recuerda los exit codes: 0 ok, 1 error, 2 sin confirmación, 3 config
   inválida/sin key, 4 completado en modo degradado (offline).
