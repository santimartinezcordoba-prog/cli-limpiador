#!/usr/bin/env python3
"""Auditoría local de referencias Git, sin imprimir contenido ni secretos."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from limpiador.secretos import contiene_secreto  # noqa: E402


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=RAIZ, stderr=subprocess.PIPE)


def patrones(datos: bytes) -> int:
    if b"\x00" in datos:
        return 0  # archivos binarios: esta auditoría se limita a texto
    return sum(contiene_secreto(linea) for linea in datos.decode("utf-8", "replace").splitlines())


def main() -> int:
    """Comprueba commits y blobs de todas las referencias locales alcanzables."""
    try:
        commits = git("rev-list", "--all").decode("ascii").splitlines()
        vistos: set[str] = set()
        entornos: set[str] = set()
        hallazgos = 0
        for commit in commits:
            mensajes = patrones(git("show", "-s", "--format=%B", commit))
            if mensajes:
                print(f"Revisar mensaje del commit {commit[:12]}: {mensajes} coincidencia(s)")
                hallazgos += mensajes
            for entrada in git("ls-tree", "-r", "-z", commit).split(b"\x00"):
                if not entrada:
                    continue
                meta, ruta = entrada.split(b"\t", 1)
                _, tipo, oid = meta.decode("ascii").split()
                if tipo != "blob":
                    continue
                nombre = PurePosixPath(ruta.decode("utf-8", "replace")).name
                if nombre == ".env" or (
                    nombre.startswith(".env.") and nombre != ".env.example"
                ):
                    if oid not in entornos:
                        entornos.add(oid)
                        print(f"Revisar archivo de entorno en commit {commit[:12]}")
                if oid in vistos:
                    continue
                vistos.add(oid)
                coincidencias = patrones(git("cat-file", "blob", oid))
                if coincidencias:
                    hallazgos += coincidencias
                    print(f"Revisar blob {oid}: {coincidencias} coincidencia(s)")
                    print(f"Ruta: {ruta.decode('utf-8', 'replace')}; commit: {commit}")
        print(f"Commits revisados: {len(commits)}; blobs únicos: {len(vistos)}")
        print(f"Archivos de entorno: {len(entornos)}; coincidencias: {hallazgos}")
        print("Auditoría de patrones: no garantiza detectar todos los secretos posibles.")
        return 1 if entornos or hallazgos else 0
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("No se pudo completar la auditoría de Git.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
