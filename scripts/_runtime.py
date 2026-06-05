#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
LOCAL_VENV_PYTHON = SKILL_ROOT / ".venv" / "bin" / "python"
REEXEC_ENV = "AI_NEWS_KEJI_REEXEC"


def missing_modules(module_names: list[str]) -> list[str]:
    return [name for name in module_names if importlib.util.find_spec(name) is None]


def dependency_hint(missing: list[str]) -> str:
    names = ", ".join(missing)
    if LOCAL_VENV_PYTHON.exists():
        return (
            f"错误：当前 Python 缺少依赖：{names}。\n"
            f"请在仓库根目录运行：{LOCAL_VENV_PYTHON} -m pip install -r requirements.txt"
        )
    return (
        f"错误：当前 Python 缺少依赖：{names}。\n"
        "请在仓库根目录运行：python3 -m pip install -r requirements.txt"
    )


def ensure_modules(module_names: list[str]) -> None:
    missing = missing_modules(module_names)
    if not missing:
        return

    current_python = Path(sys.executable).resolve()
    if (
        LOCAL_VENV_PYTHON.exists()
        and current_python != LOCAL_VENV_PYTHON.resolve()
        and os.environ.get(REEXEC_ENV) != "1"
    ):
        env = os.environ.copy()
        env[REEXEC_ENV] = "1"
        result = subprocess.run([str(LOCAL_VENV_PYTHON), *sys.argv], env=env)
        raise SystemExit(result.returncode)

    print(dependency_hint(missing), file=sys.stderr)
    raise SystemExit(1)
