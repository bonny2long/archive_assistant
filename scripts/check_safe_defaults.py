"""Bounded check: debug and dev tools stay off unless explicitly enabled."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402


def main() -> None:
    for name in ("DEBUG", "DEV_TOOLS_ENABLED"):
        os.environ.pop(name, None)

    defaults = Settings(_env_file=None)
    assert defaults.debug is False, "debug must default to off"
    assert defaults.dev_tools_enabled is False, "dev tools must default to off"
    assert defaults.api_docs_enabled is False, "API docs must default to off"

    # Turning them on is still possible, but both must be set on purpose.
    debug_only = Settings(_env_file=None, debug=True)
    assert not (debug_only.debug and debug_only.dev_tools_enabled)
    dev_tools_only = Settings(_env_file=None, dev_tools_enabled=True)
    assert not (dev_tools_only.debug and dev_tools_only.dev_tools_enabled)
    explicit = Settings(_env_file=None, debug=True, dev_tools_enabled=True)
    assert explicit.debug and explicit.dev_tools_enabled

    print("PASS - debug and dev tools are off by default")


if __name__ == "__main__":
    main()
