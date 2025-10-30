"""Helios Streamlit entrypoint shim."""
from __future__ import annotations
import importlib
from typing import Any


def _load_app_shell() -> Any:
    """Return the imported `helios.app_shell` module."""
    return importlib.import_module("helios.app_shell")


def main() -> None:
    """Entry point used by Streamlit when executing this file."""
    app_shell = _load_app_shell()
    if hasattr(app_shell, "main"):
        app_shell.main()
    elif hasattr(app_shell, "run_app"):
        app_shell.run_app()
    else:
        raise RuntimeError("helios.app_shell is missing a main/run_app entrypoint")


def run() -> None:
    """Entry point for `python app.py`."""
    app_shell = _load_app_shell()
    if hasattr(app_shell, "run_app"):
        app_shell.run_app()
    elif hasattr(app_shell, "main"):
        app_shell.main()
    else:
        raise RuntimeError("helios.app_shell is missing a run_app/main entrypoint")


if __name__ == "__main__":
    run()
