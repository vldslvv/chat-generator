"""Load implementation launch commands without importing application code."""

import json
import os
import subprocess
from pathlib import Path


def load_config():
    path = Path(os.environ.get("OFFLINE_CONFIG", "offline-delivery.json")).resolve()
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError:
        raise RuntimeError(
            f"Missing launch configuration: {path}. Set OFFLINE_CONFIG to a JSON "
            "file defining server, python and rust commands; see tools/offline_delivery/README.md."
        ) from None
    return path, config


def prepare():
    path, config = load_config()
    for entry in config.get("prepare", []):
        subprocess.run(
            entry["command"],
            cwd=(path.parent / entry.get("cwd", ".")).resolve(),
            check=True,
        )


def load_commands(port):
    path, config = load_config()
    commands = {}
    for role in ("server", "python", "rust"):
        entry = config[role]
        argv = entry["command"]
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(arg, str) for arg in argv)
        ):
            raise ValueError(f"{role}.command must be a nonempty array of strings")
        commands[role] = (
            [
                arg.replace("{port}", str(port)).replace(
                    "{url}", f"ws://127.0.0.1:{port}/ws"
                )
                for arg in argv
            ],
            (path.parent / entry.get("cwd", ".")).resolve(),
        )
    return commands


if __name__ == "__main__":
    prepare()
