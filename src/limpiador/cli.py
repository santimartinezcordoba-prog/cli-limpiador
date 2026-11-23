"""Punto de entrada de la CLI `limpiador`.

Códigos de salida (contrato centralizado en `limpiador.errores`):
- 0: todo correcto.
- 1: error de uso en tiempo de ejecución (acción o carpeta inexistente,
  o `deshacer` sin manifiesto / operación no reversible).
- 2: falta confirmación (sin TTY y sin ``--si``) o flags incompatibles.
- 3: el fichero de configuración no es válido (o `comprobar-ia` sin API key).
- 4: completado en modo degradado (acción IA sin red) o `comprobar-ia` sin
  conexión con el centro.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Final

import typer
from rich.console import Console
from rich.text import Text

from limpiador import __version__
from limpiador.acciones import AccionError, Operacion, buscar_accion, planificar
from limpiador.acciones import ejecutar as ejecutar_plan
from limpiador.config import (
    OPERACIONES_IA,
    Accion,
    Config,
    ConfigInvalidaError,
    cargar_config,
)
from limpiador.errores import (
    EXIT_CONFIG_INVALIDA,
    EXIT_ERROR,
    EXIT_OFFLINE,
    EXIT_OK,
    EXIT_SIN_CONFIRMAR,
)
from limpiador.ia import CentroIA
from limpiador.papelera import (
    PapeleraError,
    deshacer_operacion,
    resolver_papelera_cli,
)
from limpiador.secretos import redact
from limpiador.tabla import tabla_acciones, tabla_ficheros, tabla_operaciones

RESPUESTAS_AFIRMATIVAS: Final[frozenset[str]] = frozenset({"s", "si", "sí", "y", "yes"})

console = Console()
app = typer.Typer(
    name="limpiador",
    help="Limpia y ordena ficheros según acciones definidas en un JSON.",
    no_args_is_help=True,
    add_completion=False,
)


def main() -> None:
    """Wrapper del entry point (referenciado en pyproject.toml)."""
    app()


def _stdin_interactivo() -> bool:
    """True si hay un terminal real conectado a stdin.

    Está en una función aparte para poder simular su contrario en los tests.
    """
    return sys.stdin.isatty()


@app.callback()
def principal(
    ctx: typer.Context,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            help="Ruta del fichero de acciones (por defecto ./acciones.json).",
            show_default=True,
        ),
    ] = Path("./acciones.json"),
) -> None:
    """Guarda la ruta del fichero de configuración para todas las órdenes."""
    ctx.obj = config


def _cargar_config_o_salir(ruta: Path) -> Config:
    """Carga la configuración; si es inválida, imprime los fallos y sale con 3."""
    try:
        return cargar_config(ruta)
    except ConfigInvalidaError as exc:
        console.print(f"[bold red]El fichero '{ruta}' no es válido:[/]")
        for error in exc.errores:
            console.print(f"  [red]✗[/] {error}")
        raise typer.Exit(EXIT_CONFIG_INVALIDA) from exc


def _resolver_carpeta_o_salir(carpeta: Path) -> None:
    """Comprueba que la carpeta existe antes de cualquier operación."""
    if not carpeta.exists():
        console.print(f"[red]✗ La carpeta '{carpeta}' no existe.[/]")
        raise typer.Exit(EXIT_ERROR)
    if not carpeta.is_dir():
        console.print(f"[red]✗ '{carpeta}' no es una carpeta.[/]")
        raise typer.Exit(EXIT_ERROR)


def _buscar_accion_o_salir(config: Config, nombre: str) -> Accion:
    """Devuelve la acción pedida; si no existe, explica las disponibles y sale 1."""
    try:
        return buscar_accion(config, nombre)
    except AccionError as exc:
        console.print(f"[red]✗ {exc}[/]")
        raise typer.Exit(EXIT_ERROR) from exc


@app.command()
def version() -> None:
    """Muestra la versión instalada de limpiador."""
    console.print(f"limpiador {__version__}")


@app.command()
def doctor() -> None:
    """Diagnóstico del entorno de instalación. Sale con 0 si todo es correcto.

    Comprueba la versión de Python, las dependencias (typer, rich, pydantic)
    y que la CLI está correctamente instalada. Es el `limpiador doctor` del
    job `install-smoke` de CI: si sale 0, otra persona puede usar la CLI.
    """
    import importlib.metadata

    comprobaciones: list[tuple[bool, str, str]] = []
    version_py = sys.version.split()[0]
    comprobaciones.append(
        (sys.version_info >= (3, 10), "python", f"{version_py} (se requiere >= 3.10)")
    )
    for dependencia in ("typer", "rich", "pydantic"):
        try:
            comprobaciones.append(
                (True, dependencia, importlib.metadata.version(dependencia))
            )
        except importlib.metadata.PackageNotFoundError:
            comprobaciones.append((False, dependencia, "no instalada"))
    try:
        comprobaciones.append(
            (True, "limpiador", importlib.metadata.version("limpiador"))
        )
    except importlib.metadata.PackageNotFoundError:
        comprobaciones.append((False, "limpiador", "no instalada como paquete"))

    for ok, nombre, detalle in comprobaciones:
        simbolo = "green]✓" if ok else "red]✗"
        console.print(f"[{simbolo}] {nombre}: {detalle}")
    if not all(ok for ok, _, _ in comprobaciones):
        console.print("[bold red]Entorno no apto para limpiador.[/]")
        raise typer.Exit(EXIT_ERROR)
    console.print("[bold green]Todo correcto: el entorno ejecuta limpiador.[/]")


@app.command()
def listar(
    ctx: typer.Context,
    carpeta: Annotated[
        Path, typer.Argument(help="Carpeta a listar (por defecto, la actual).")
    ] = Path("."),
) -> None:
    """Muestra una tabla con nombre, tipo, tamaño y fecha de cada fichero."""
    _resolver_carpeta_o_salir(carpeta)
    entradas = sorted(
        (e for e in carpeta.iterdir() if not e.is_dir()), key=lambda e: e.name
    )
    if not entradas:
        console.print(f"La carpeta '[bold]{carpeta}[/]' no contiene ficheros.")
        return
    console.print(tabla_ficheros(carpeta, entradas))


@app.command()
def acciones(ctx: typer.Context) -> None:
    """Lista las acciones definidas en el fichero de configuración."""
    config = _cargar_config_o_salir(Path(ctx.obj))
    console.print(tabla_acciones(config.version, config.acciones))


@app.command()
def validar(
    ctx: typer.Context,
    salida_json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emite el resultado como JSON estructurado (para scripts).",
        ),
    ] = False,
) -> None:
    """Comprueba el fichero de acciones. Sale con 3 si es inválido."""
    ruta = Path(ctx.obj)
    try:
        config = cargar_config(ruta)
    except ConfigInvalidaError as exc:
        if salida_json:
            typer.echo(
                json.dumps(
                    {"valido": False, "archivo": str(ruta), "errores": exc.errores},
                    ensure_ascii=False,
                )
            )
            raise typer.Exit(EXIT_CONFIG_INVALIDA) from exc
        console.print(f"[bold red]El fichero '{ruta}' no es válido:[/]")
        for error in exc.errores:
            console.print(f"  [red]✗[/] {error}")
        raise typer.Exit(EXIT_CONFIG_INVALIDA) from exc
    if salida_json:
        typer.echo(
            json.dumps(
                {
                    "valido": True,
                    "archivo": str(ruta),
                    "config_version": config.version,
                    "acciones": len(config.acciones),
                    "errores": [],
                },
                ensure_ascii=False,
            )
        )
        return
    console.print(
        f"[bold green]✓ '{ruta}' es válido[/] "
        f"(config v{config.version}, {len(config.acciones)} acción(es))."
    )


@app.command("ejecutar")
def ejecutar_accion(
    ctx: typer.Context,
    nombre: Annotated[str, typer.Argument(help="Nombre de la acción a ejecutar.")],
    carpeta: Annotated[
        Path, typer.Argument(help="Carpeta sobre la que actuar (por defecto, la actual).")
    ] = Path("."),
    simular: Annotated[
        bool, typer.Option("--simular", help="Muestra qué haría la acción sin tocar nada.")
    ] = False,
    si: Annotated[
        bool, typer.Option("--si", help="Ejecuta sin pedir confirmación (para scripts).")
    ] = False,
) -> None:
    """Ejecuta una acción con simulación, confirmación interactiva o `--si`."""
    if simular and si:
        console.print("[red]✗ '--simular' y '--si' son incompatibles.[/]")
        raise typer.Exit(EXIT_SIN_CONFIRMAR)

    config = _cargar_config_o_salir(Path(ctx.obj))
    accion = _buscar_accion_o_salir(config, nombre)
    _resolver_carpeta_o_salir(carpeta)

    try:
        plan = planificar(accion, carpeta)
    except AccionError as exc:
        console.print(f"[red]✗ {redact(str(exc))}[/]")
        raise typer.Exit(EXIT_ERROR) from exc

    if not plan:
        console.print(
            f"Ningún fichero de '[bold]{carpeta}[/]' coincide con '{nombre}'. "
            "No hay nada que hacer."
        )
        raise typer.Exit(EXIT_OK)

    if accion.operacion in OPERACIONES_IA:
        # Motor IA (sin Typer dentro): sin key ni red degrada a heurística
        # (exit 4). El plan IA es orientativo: la tabla solo se pinta en
        # --simular; en modo real el motor recalcula objetivo y destino.
        if simular:
            console.print(tabla_operaciones(plan, simulacion=True))
            console.print(
                "[yellow]Simulación: no se ha modificado nada (la IA decide "
                "la salida al ejecutar).[/]"
            )
            raise typer.Exit(EXIT_OK)
        raise typer.Exit(_ejecutar_ia_o_salir(accion, nombre, carpeta, plan, si=si))

    console.print(tabla_operaciones(plan, simulacion=simular))

    if simular:
        console.print("[yellow]Simulación: no se ha modificado nada.[/]")
        raise typer.Exit(EXIT_OK)

    if not si:
        if not _stdin_interactivo():
            console.print(
                "[red]✗ Sin terminal interactivo la ejecución requiere --si "
                "(o usa --simular).[/]"
            )
            raise typer.Exit(EXIT_SIN_CONFIRMAR)
        _pedir_confirmacion_o_salir(nombre, carpeta, plan)

    try:
        bitacora, ruta_manifiesto = ejecutar_plan(accion, carpeta, plan)
    except (AccionError, OSError) as exc:
        # `redact` SIEMPRE: un error del motor puede arrastrar la key del
        # centro (p. ej. un volcado de la cabecera Authorization). La consola
        # solo puede ver la máscara.
        console.print(f"[red]✗ Error al ejecutar: {redact(str(exc))}[/]")
        raise typer.Exit(EXIT_ERROR) from exc

    for linea in bitacora:
        console.print(f"  [green]✓[/] {redact(linea)}")
    console.print(f"[bold green]Acción '{nombre}' ejecutada.[/]")
    if ruta_manifiesto is not None:
        console.print(
            f"[dim]Manifiesto: {ruta_manifiesto} — "
            "puedes revertirlo con 'limpiador deshacer'.[/]"
        )


@app.command()
def deshacer(
    n: Annotated[
        int,
        typer.Argument(min=1, help="Cuántas ejecuciones saltar: 1 = la última."),
    ] = 1,
    carpeta: Annotated[
        Path,
        typer.Option("--carpeta", help="Carpeta donde se ejecutó la acción."),
    ] = Path("."),
    papelera: Annotated[
        str | None,
        typer.Option(
            "--papelera",
            help="Subcarpeta de papelera personalizada (por defecto 'papelera').",
        ),
    ] = None,
) -> None:
    """Revierte la última operación real registrada por la papelera.

    Lee el manifiesto N-ésimo más reciente y mueve cada fichero de vuelta a
    su ruta original. Si el original ya existe, no sobrescribe: crea
    `nombre.restaurado.ext`. Sale con 1 si no hay nada que deshacer o la
    operación no es reversible (contuvo borrados definitivos).
    """
    _resolver_carpeta_o_salir(carpeta)
    try:
        papelera_base = resolver_papelera_cli(carpeta.resolve(), papelera)
        manifiesto, bitacora = deshacer_operacion(papelera_base, n)
    except (PapeleraError, OSError) as exc:
        console.print(f"[red]✗ No se puede deshacer: {exc}[/]")
        raise typer.Exit(EXIT_ERROR) from exc

    for linea in bitacora:
        color = "yellow" if linea.startswith("AVISO") else "green"
        console.print(f"  [{color}]✓[/] {linea}")
    console.print(
        f"[bold green]Deshecha la operación '{manifiesto.op_id}' "
        f"de la acción '{manifiesto.accion}' ({manifiesto.timestamp}).[/]"
    )


@app.command("comprobar-ia")
def comprobar_ia(
    salida_json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emite el resultado como JSON estructurado (para scripts).",
        ),
    ] = False,
) -> None:
    """Smoke test de la IA del centro. Exit: 0 ok, 3 sin key, 4 sin red.

    Comprueba (en este orden) que la API key está PRESENTE —sin imprimirla
    nunca, solo «presente/ausente»— y lanza un ping mínimo al modelo con
    timeout. Si algo falla, la salida (texto o `--json`) está redactada: la
    clave no puede aparecer ni en el mensaje ni en el log.
    """
    from limpiador.ia import (
        COMPROBACION_OK,
        COMPROBACION_SIN_KEY,
        comprobar_centro,
    )

    centro = CentroIA.desde_entorno()
    resultado = comprobar_centro(centro)
    if salida_json:
        typer.echo(
            json.dumps(
                {
                    "estado": resultado.estado,
                    "key": "presente" if resultado.tiene_key else "ausente",
                    "modelo": resultado.modelo,
                    "latencia_s": (
                        round(resultado.latencia_s, 3)
                        if resultado.latencia_s is not None
                        else None
                    ),
                    "detalle": resultado.detalle,
                },
                ensure_ascii=False,
            )
        )
    else:
        clave = "presente" if resultado.tiene_key else "ausente"
        console.print(f"[bold]key[/]: {clave}")
        console.print(f"[bold]modelo[/]: {resultado.modelo}")
        if resultado.estado == COMPROBACION_OK:
            assert resultado.latencia_s is not None
            console.print(
                f"[green]✓ ok[/] — el centro respondió en "
                f"[bold]{resultado.latencia_s:.2f} s[/]."
            )
        elif resultado.estado == COMPROBACION_SIN_KEY:
            console.print(
                Text(
                    "[red]✗ sin key[/] — define LIMPIADOR_IA_KEY en .env o en "
                    "el entorno. Las acciones IA siguen usables porque "
                    "degradan a heurística local ([modo offline])."
                )
            )
            if resultado.detalle:
                console.print(f"[dim]{redact(resultado.detalle)}[/]")
        else:  # COMPROBACION_SIN_RED
            console.print(
                "[yellow]⚠ sin red[/] — la key está presente pero el centro "
                "no respondió (timeout/5xx/sin conexión)."
            )
            console.print(f"[dim]{redact(resultado.detalle)}[/]")
            console.print(
                "[dim]Las acciones IA degradan a heurística local: nadie se "
                "queda sin resultado.[/] "
                "Salida: completado en modo degradado (exit 4)."
            )
    if resultado.estado == COMPROBACION_OK:
        raise typer.Exit(EXIT_OK)
    if resultado.estado == COMPROBACION_SIN_KEY:
        raise typer.Exit(EXIT_CONFIG_INVALIDA)
    raise typer.Exit(EXIT_OFFLINE)  # sin red: degradado, no crash


def _ejecutar_ia_o_salir(
    accion: Accion, nombre: str, carpeta: Path, plan: list[Operacion], *, si: bool
) -> int:
    """Ejecuta una acción IA con la misma política de confirmación que el resto.

    La ejecución IA real NUNCA se lanza sin confirmación (`--si` o `s/N`):
    el plan ya mostrado es orientativo y el motor IA vuelve a contar los
    objetivos sobre la carpeta ya validada. Salida siempre redactada.
    """
    from limpiador import acciones_ia

    if not si:
        if not _stdin_interactivo():
            console.print(
                "[red]✗ Sin terminal interactivo la ejecución requiere --si "
                "(o usa --simular).[/]"
            )
            return EXIT_SIN_CONFIRMAR
        try:
            _pedir_confirmacion_o_salir(nombre, carpeta, plan)
        except typer.Exit as exc:
            assert isinstance(exc.exit_code, int)
            return exc.exit_code

    try:
        _, raiz, objetivos, _ = acciones_ia.planificar_ia_desde(accion, carpeta)
        bitacora, codigo, ruta_log = acciones_ia.ejecutar_ia(accion, raiz, objetivos)
    except (acciones_ia.IAError, AccionError, OSError) as exc:
        console.print(f"[red]✗ Error al ejecutar la acción IA: {redact(str(exc))}[/]")
        return EXIT_ERROR

    for linea in bitacora:
        # El aviso `[modo offline]` se pinta como Text LITERAL: si se dejase
        # a Rich, el corchete se leería como markup y la línea (o el aviso)
        # desaparecería de la consola.
        if linea.startswith("[modo offline]"):
            aviso = Text("  ✓ ", style="yellow")
            aviso.append("[modo offline] ", style="bold yellow")
            aviso.append(redact(linea[len("[modo offline]") :]))
            console.print(aviso)
        else:
            consola_linea = Text("  ✓ ", style="green") + Text(redact(linea))
            console.print(consola_linea)
    if codigo == EXIT_OFFLINE:
        aviso_final = Text("⚠ ", style="yellow")
        aviso_final.append("[modo offline] ", style="bold yellow")
        aviso_final.append(
            "sin key o sin conexión: completado en modo degradado con "
            "heurística local. Nada se ha perdido."
        )
        console.print(aviso_final)
        if ruta_log is not None:
            console.print(f"[dim]Log de auditoría: {ruta_log}[/]")
        console.print(f"[bold yellow]Acción '{nombre}' completada en modo degradado.[/]")
        return EXIT_OFFLINE
    console.print(f"[bold green]Acción '{nombre}' ejecutada con la IA del centro.[/]")
    if ruta_log is not None:
        console.print(f"[dim]Log de auditoría: {ruta_log}[/]")
    return EXIT_OK


def _pedir_confirmacion_o_salir(nombre: str, carpeta: Path, plan: list[Operacion]) -> None:
    """Pide confirmación 's/N' al usuario; sale limpiamente si dice que no."""
    try:
        respuesta = typer.prompt(
            f"¿Ejecutar '{nombre}' ({len(plan)} operación(es)) sobre '{carpeta}'? [s/N]",
            default="n",
            show_default=False,
        )
    except typer.Abort as exc:
        console.print("[yellow]Cancelado.[/]")
        raise typer.Exit(EXIT_SIN_CONFIRMAR) from exc
    if respuesta.strip().lower() not in RESPUESTAS_AFIRMATIVAS:
        console.print("[yellow]Cancelado: no se ha tocado nada.[/]")
        raise typer.Exit(EXIT_OK)
