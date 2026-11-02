"""Punto de entrada de la CLI `limpiador`.

Códigos de salida:
- 0: todo correcto.
- 1: error de uso en tiempo de ejecución (acción o carpeta inexistente).
- 2: falta confirmación (sin TTY y sin ``--si``) o flags incompatibles.
- 3: el fichero de configuración no es válido.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Final

import typer
from rich.console import Console

from limpiador import __version__
from limpiador.acciones import AccionError, Operacion, buscar_accion, planificar
from limpiador.acciones import ejecutar as ejecutar_plan
from limpiador.config import Accion, Config, ConfigInvalidaError, cargar_config
from limpiador.tabla import tabla_acciones, tabla_ficheros, tabla_operaciones

EXIT_OK: Final = 0
EXIT_ERROR: Final = 1
EXIT_SIN_CONFIRMAR: Final = 2
EXIT_CONFIG_INVALIDA: Final = 3

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
def validar(ctx: typer.Context) -> None:
    """Comprueba el fichero de acciones. Sale con 3 si es inválido."""
    ruta = Path(ctx.obj)
    config = _cargar_config_o_salir(ruta)
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
        console.print(f"[red]✗ {exc}[/]")
        raise typer.Exit(EXIT_ERROR) from exc

    if not plan:
        console.print(
            f"Ningún fichero de '[bold]{carpeta}[/]' coincide con '{nombre}'. "
            "No hay nada que hacer."
        )
        raise typer.Exit(EXIT_OK)

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
        bitacora = ejecutar_plan(accion, carpeta, plan)
    except (AccionError, OSError) as exc:
        console.print(f"[red]✗ Error al ejecutar: {exc}[/]")
        raise typer.Exit(EXIT_ERROR) from exc

    for linea in bitacora:
        console.print(f"  [green]✓[/] {linea}")
    console.print(f"[bold green]Acción '{nombre}' ejecutada.[/]")


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
