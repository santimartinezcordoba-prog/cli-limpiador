"""Tests de `limpiador ejecutar`: simulación, ejecución real y casos feos.

Todos los movimientos/borrados ocurren dentro de `tmp_path`. Ningún test
tocan nunca ficheros reales del sistema.
"""

from __future__ import annotations

from typer.testing import CliRunner

from conftest import instantanea, llamar, salida_normalizada
from limpiador.cli import EXIT_ERROR, EXIT_OK, EXIT_SIN_CONFIRMAR


# --------------------------------------------------------------------------- #
# Camino feliz: simulación (no toca el disco)
# --------------------------------------------------------------------------- #
def test_simular_muestra_el_plan_sin_tocar_nada(
    runner: CliRunner, carpeta_pruebas, config_valida
) -> None:
    """`--simular` lista lo que haría pero deja la carpeta intacta."""
    antes = instantanea(carpeta_pruebas)

    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(carpeta_pruebas), "--simular"],
        config=config_valida,
    )
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_OK
    # Anuncia que es una simulación y menciona los ficheros que movería.
    assert "Simulación" in salida
    assert "foto.png" in salida
    # La prueba de fuego: ni un solo byte cambió en el disco.
    assert instantanea(carpeta_pruebas) == antes
    # Y no se ha creado la carpeta de destino.
    assert not (carpeta_pruebas / "imagenes").exists()


# --------------------------------------------------------------------------- #
# Camino feliz: ejecución real con --si
# --------------------------------------------------------------------------- #
def test_si_mueve_las_imagenes_de_verdad(
    runner: CliRunner, carpeta_pruebas, config_valida
) -> None:
    """`--si` ejecuta sin preguntar: las imágenes acaban en imagenes/."""
    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(carpeta_pruebas), "--si"],
        config=config_valida,
    )

    assert resultado.exit_code == EXIT_OK
    # foto.png y selfie.jpg ya no están en la raíz...
    assert not (carpeta_pruebas / "foto.png").exists()
    assert not (carpeta_pruebas / "selfie.jpg").exists()
    # ...y sí están dentro de la carpeta imagenes/.
    assert (carpeta_pruebas / "imagenes" / "foto.png").is_file()
    assert (carpeta_pruebas / "imagenes" / "selfie.jpg").is_file()
    # Los ficheros que no casan con los patrones se quedan donde estaban.
    assert (carpeta_pruebas / "informe.pdf").is_file()
    # El contenido se conserva íntegro tras el movimiento.
    assert (carpeta_pruebas / "imagenes" / "foto.png").read_bytes() == (
        b"contenido de foto.png"
    )


def test_si_borra_temporales(runner: CliRunner, carpeta_pruebas, config_valida) -> None:
    """La acción 'borrar-temporales' elimina los .tmp y no toca lo demás."""
    (carpeta_pruebas / "basura.tmp").write_text("x", encoding="utf-8")

    resultado = llamar(
        runner, ["ejecutar", "borrar-temporales", str(carpeta_pruebas), "--si"],
        config=config_valida,
    )

    assert resultado.exit_code == EXIT_OK
    assert not (carpeta_pruebas / "basura.tmp").exists()
    assert not (carpeta_pruebas / "datos.tmp").exists()
    # Un .pdf no debe borrarse jamás con esta acción.
    assert (carpeta_pruebas / "informe.pdf").is_file()


def test_si_renombra_con_sufijo(
    runner: CliRunner, carpeta_pruebas, config_valida
) -> None:
    """La operación 'renombrar' añade el sufijo antes de la extensión."""
    resultado = llamar(
        runner, ["ejecutar", "renombrar-viejos", str(carpeta_pruebas), "--si"],
        config=config_valida,
    )

    assert resultado.exit_code == EXIT_OK
    # readme.txt pasa a llamarse readme-revisar.txt.
    assert not (carpeta_pruebas / "readme.txt").exists()
    assert (carpeta_pruebas / "readme-revisar.txt").is_file()


def test_es_no_recursivo_con_ordenar_documentos(
    runner: CliRunner, carpeta_pruebas, config_valida
) -> None:
    """Las acciones solo actúan sobre el primer nivel, no entran en subcarpetas."""
    resultado = llamar(
        runner, ["ejecutar", "ordenar-documentos", str(carpeta_pruebas), "--si"],
        config=config_valida,
    )

    assert resultado.exit_code == EXIT_OK
    # informe.pdf (primer nivel) se mueve...
    assert (carpeta_pruebas / "documentos" / "informe.pdf").is_file()
    # ...pero notas.pdf, dentro de sub/, debe quedarse intacto.
    assert (carpeta_pruebas / "sub" / "notas.pdf").is_file()


# --------------------------------------------------------------------------- #
# Seguridad: sin TTY y sin --si hay que negarse a ejecutar (código 2)
# --------------------------------------------------------------------------- #
def test_sin_tty_y_sin_si_se_niega_y_sale_2(
    runner: CliRunner, carpeta_pruebas, config_valida, monkeypatch
) -> None:
    """En un script sin terminal, sin --si/--simular, no ejecuta y sale con 2."""
    # Forzamos que no haya terminal interactivo (como en un cron o un pipe).
    monkeypatch.setattr("limpiador.cli._stdin_interactivo", lambda: False)

    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(carpeta_pruebas)],
        config=config_valida,
    )
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_SIN_CONFIRMAR
    # Pedir explícitamente --si en contexto no interactivo.
    assert "--si" in salida
    # Y, por supuesto, no mueve nada.
    assert (carpeta_pruebas / "foto.png").is_file()


def test_confirmacion_afirmativa_ejecuta(
    runner: CliRunner, carpeta_pruebas, config_valida, monkeypatch
) -> None:
    """Con terminal y respuesta 's', la CLI ejecuta tras preguntar."""
    monkeypatch.setattr("limpiador.cli._stdin_interactivo", lambda: True)

    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(carpeta_pruebas)],
        config=config_valida,
        entrada="s\n",
    )

    assert resultado.exit_code == EXIT_OK
    assert (carpeta_pruebas / "imagenes" / "foto.png").is_file()


def test_confirmacion_negativa_no_toca_nada(
    runner: CliRunner, carpeta_pruebas, config_valida, monkeypatch
) -> None:
    """Con terminal y respuesta 'n', la CLI se cancela sin modificar nada."""
    monkeypatch.setattr("limpiador.cli._stdin_interactivo", lambda: True)
    antes = instantanea(carpeta_pruebas)

    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(carpeta_pruebas)],
        config=config_valida,
        entrada="n\n",
    )
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_OK
    assert "Cancelado" in salida
    assert instantanea(carpeta_pruebas) == antes


def test_simular_y_si_juntas_es_error(runner: CliRunner, carpeta_pruebas, config_valida) -> None:
    """Pedir a la vez --simular y --si es contradictorio: se rechaza con código 2."""
    resultado = llamar(
        runner,
        ["ejecutar", "mover-imagenes", str(carpeta_pruebas), "--simular", "--si"],
        config=config_valida,
    )
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_SIN_CONFIRMAR
    assert "incompatibles" in salida


# --------------------------------------------------------------------------- #
# Seguridad: enlaces simbólicos que apuntan fuera de la carpeta objetivo
# --------------------------------------------------------------------------- #
def test_no_sigue_enlaces_simbolicos_fuera_de_la_carpeta(
    runner: CliRunner, tmp_path, config_valida
) -> None:
    """Un .png que es un enlace fuera de la carpeta no se mueve ni se sigue."""
    objetivo = tmp_path / "objetivo"
    objetivo.mkdir()
    fuera = tmp_path / "fuera.png"
    fuera.write_text("importante", encoding="utf-8")
    # foto.png dentro de la carpeta es un enlace a un fichero de fuera.
    (objetivo / "foto.png").symlink_to(fuera)

    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(objetivo), "--si"],
        config=config_valida,
    )

    # Ningún fichero real coincide (solo había un enlace) -> nada que hacer.
    assert resultado.exit_code == EXIT_OK
    # El enlace y su destino fuera de la carpeta siguen en su sitio.
    assert fuera.read_text(encoding="utf-8") == "importante"
    assert (objetivo / "foto.png").is_symlink()


# --------------------------------------------------------------------------- #
# Caso feo 2: acción inexistente
# --------------------------------------------------------------------------- #
def test_accion_inexistente_muestra_error_y_alternativas(
    runner: CliRunner, carpeta_pruebas, config_valida
) -> None:
    """Si la acción no existe, error claro + lista de acciones válidas."""
    resultado = llamar(
        runner, ["ejecutar", "no-existe", str(carpeta_pruebas), "--simular"],
        config=config_valida,
    )
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_ERROR
    assert "no existe la acción 'no-existe'" in salida
    # Ayuda al usuario enumerando las acciones reales.
    assert "mover-imagenes" in salida


# --------------------------------------------------------------------------- #
# Caso feo 3: carpeta inexistente al ejecutar
# --------------------------------------------------------------------------- #
def test_carpeta_inexistente_al_ejecutar(
    runner: CliRunner, tmp_path, config_valida
) -> None:
    """Si la carpeta objetivo no existe, error claro y código 1."""
    ruta_falsa = tmp_path / "jamas-existio"

    resultado = llamar(
        runner, ["ejecutar", "mover-imagenes", str(ruta_falsa), "--si"],
        config=config_valida,
    )
    salida = salida_normalizada(resultado.output)

    assert resultado.exit_code == EXIT_ERROR
    assert "no existe" in salida
