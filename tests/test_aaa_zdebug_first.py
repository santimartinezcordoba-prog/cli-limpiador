from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any

from typer.testing import CliRunner

from limpiador.cli import app


def _plain(txt: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", txt)


def test_aaa_zdebug_primera_llamada() -> None:
    runner = CliRunner()
    r1 = runner.invoke(app, ["--help"])
    r2 = runner.invoke(app, ["--help"])
    info: dict[str, Any] = {
        "TERM": os.environ.get("TERM"),
        "COLUMNS": os.environ.get("COLUMNS"),
        "term_size": str(shutil.get_terminal_size()),
        "len1": len(r1.output),
        "cfg1": "--config" in _plain(r1.output),
        "len2": len(r2.output),
        "cfg2": "--config" in _plain(r2.output),
    }
    print("\nZFIRST " + json.dumps(info, ensure_ascii=False))
    print("ZP1 " + json.dumps(_plain(r1.output), ensure_ascii=False))
    assert _plain(r1.output).count("--config") >= 1, "ver volcado arriba"
