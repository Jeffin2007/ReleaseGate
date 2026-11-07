"""
ReleaseGate Model Context Protocol (MCP) Server.
Adheres to ReleaseGate Frozen Architecture Baseline v1.0.
Exposes the 12 frozen MCP governance tools, 4 resources, and 4 prompts.
"""

from pathlib import Path
import sys

# Ensure apps/api and root are in sys.path for submodule resolution
_root = str(Path(__file__).resolve().parent.parent)
_api = str(Path(__file__).resolve().parent.parent / "apps" / "api")

if _root not in sys.path:
    sys.path.insert(0, _root)
if _api not in sys.path:
    sys.path.insert(0, _api)

__version__ = "1.0.0"
