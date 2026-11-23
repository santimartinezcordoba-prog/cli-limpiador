# ADR-0002 — IA como acción opcional: modo sin red + redacción de secretos

- Estado: Aceptado
- Fecha: 2026-11-18 (semana 3)
- Relacionado: ADR-0001 (registro y separación Accion/Motor)

## Contexto

La semana 3 añade IA del centro (API OpenAI-compatible) a la CLI. Tres
amenazas/necesidades sin resolver:

1. **Secretos**: la API key del centro puede acabar en el código, en un
   commit, en la consola o en un log. Cualquiera de las cuatro es un
   incidente.
2. **Disponibilidad**: el centro puede estar caído (503), tardar (timeout)
   o el usuario puede no tener key. Una CLI de limpieza que petan no se
   usa: «nadie puede quedarse tirado sin red».
3. **Deriva de dependencias**: el MCP `context7` ayuda a consultar doc
   (p. ej. la de `httpx`), pero si se usara sin control se convertiría en
   una muleta invisible y en coste por sesión.

## Decisión

1. **IA como acción opcional, no como núcleo.** `resumir-texto` y
   `clasificar-ficheros` son dos operaciones más de la whitelist; el 90 %
   de la CLI (listar, mover, borrar, dedup, papelera…) funciona sin IA,
   sin key y sin conexión. El núcleo del producto NO depende de la red.
2. **La key solo vive en `.env` o en el entorno.** `.env` está en
   `.gitignore`; `.env.example` (sin valores) es el único fichero de
   variables versionado. Un escáner de secretos (`scripts/escaner_secretos.py`,
   job `secret-scan` de CI + test `test_no_hay_claves_en_repo`) bloquea el
   merge si un patrón de API key aparece en cualquier fichero versionado.
3. **Redacción obligatoria de secretos.** `secretos.redact()` enmascara
   `sk-…`, `Bearer …`, `Basic …` y asignaciones `api_key=…` ANTES de
   imprimir o escribir en el log de auditoría; `SinRedError` nace ya
   redactado. El estado de la key solo se muestra como «presente/ausente».
4. **Modo sin red (degradación heurística).** Si falta la key o falla la
   conexión (timeout, 5xx, fallo de red/DNS/TLS), la acción NO peta: aplica
   una heurística local determinista (resumen = primeras N frases +
   métricas; clasificación = palabras clave del contenido, luego extensión)
   y avisa `[modo offline]` con exit code 4 («completado en modo
   degradado»). El modo `estricto` (`"modo_offline": "estricto"`) es la
   opción para quien prefiera fallo antes que heurística.
5. **MCP `context7` apagado por defecto.** En `opencode.json` queda con
   `"enabled": false`; se enciende puntualmente con `/mcps` SOLO para
   consultar documentación (caso real: la doc de `httpx`). Es una ayuda de
   desarrollo, no una dependencia runtime: la CLI se construye, se testea
   y se libera sin él.

## Consecuencias

- Positivas:
  - «Sin filtrar la clave» deja de ser una promesa: está garantizada por
    CI (escáner), por código (`redact` en toda salida) y por tests
    (`test_redacta_clave_en_error`, `test_accion_ia_offline_log_sin_clave`).
  - «Sin dejar a nadie tirado sin red»: la acción IA termina SIEMPRE con
    resultado (exit 0 con IA, exit 4 con heurística + aviso). Nadie
    recibe un traceback por un centro caído.
  - Contrato de exit codes ampliado y estable: 3 = config inválida/sin
    key, 4 = degradado. Scripts y CI pueden distinguir los estados.
  - La auditoría con el MCP detectó y documentó obsolescencias REALES de
    httpx 0.28 (abajo) antes de que petaran en producción.
- Neutras/negativas:
  - Dos rutas por acción IA (IA real / heurística): el doble de casos de
    test (mitigado con el cliente inyectable `CentroIA._nuevo_cliente`:
    los tests usan mock y NUNCA red).
  - La heurística offline es peor que la IA: por eso el aviso y el exit 4
    la señalan siempre; el usuario decide si reintentar con red.
  - El escáner de secretos puede dar falsos positivos en fixtures de test:
    se gestionan con el marcador `# scanner: ejemplo` (y el test audita
    también al escáner), no con huecos en los patrones.

## Obsolescencia httpx 0.28 detectada con el MCP (context7 → doc oficial)

1. **`httpx.Client(proxies={...})` está ELIMINADO en 0.28.** `proxies`
   (heredado de `requests`) quedó deprecated en 0.26 («Use 'proxy' or
   'mounts' instead») y en 0.28 su paso lanza
   `TypeError: Client.__init__() got an unexpected keyword argument
   'proxies'`. La forma correcta es `proxy=<url>` (único) o
   `mounts={patrón: HTTPTransport(proxy=...)}` (routing por
   esquema/dominio/puerto). Nuestro cliente (`ia.py`) usa la forma viva
   (`base_url` + `timeout` + `follow_redirects` + `verify=<CA>`) y el test
   `test_forma_obsoleta_proxies_falla` fija en ejecución que la forma muerta
   es `TypeError` — si alguien la reintroduce por costumbre, CI lo recuerda.
2. **`verify=False` como callar el TLS auto-firmado.** Sigue siendo sintaxis
   válida en 0.28 pero es el opt-out documentado que DESACTIVA la
   comprobación de certificados (MITM). Con el CA auto-firmado del centro la
   forma correcta es `verify=<ruta-CA>` (`LIMPIADOR_CA_BUNDLE`); `False`
   queda reservado a transportes simulados de test.

## Verificación

- `limpiador comprobar-ia`: key «presente/ausente» (jamás el valor), ping
  con timeout y latencia; exit 0/3/4 según ok/sin key/sin red; `--json`
  parseable.
- Suite: 88 tests en verde con `--cov-fail-under=80`, todos offline
  (monkeypatch del cliente httpx; NUNCA peticiones reales).
