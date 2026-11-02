from __future__ import annotations

import json
import os
import re
from typing import Any

from typer.testing import CliRunner

from limpiador.cli import app


def test_zdebug_ayuda() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["--help"])
    plain = re.sub(r"\x1b\[[0-9;]*m", "", res.output)
    info: dict[str, Any] = {
        "env_COLUMNS_os": os.environ.get("COLUMNS"),
        "exit": res.exit_code,
        "len_output": len(res.output),
        "has_config": "--config" in plain,
        "tail": res.output[-120:],
    }
    print("\nZDUMP " + json.dumps(info, ensure_ascii=False))
    print("ZPLAIN " + json.dumps(plain, ensure_ascii=False))
