"""
Import bridge for the hyphenated ``mcp-server/`` directory.

Mirrors the ``local_worker`` bridge so that ``import mcp_server`` resolves to the
official Python MCP SDK server living in ``mcp-server/`` on every platform,
without depending on filesystem symlinks.
"""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent

# The MCP plane depends only on the repository root (engines, local_worker);
# it must never need the FastAPI/PostgreSQL control plane on sys.path.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_SERVER_DIR = str((_ROOT / "mcp-server").resolve())
if _SERVER_DIR not in __path__:  # type: ignore[name-defined]
    __path__.insert(0, _SERVER_DIR)  # type: ignore[name-defined]

__version__ = "1.0.0"
