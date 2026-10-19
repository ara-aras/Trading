"""Connect to a running DaVinci Resolve from an ordinary Python process.

The one non-obvious part is PYTHONHOME. Without it, `import DaVinciResolveScript` dies with

    SystemError: initialization of fusionscript failed without raising an exception

which reads like a version mismatch or a disabled preference and is neither - fusionscript
links python3.dll (the stable ABI) and cannot locate a usable interpreter root on its own
when Python was launched from somewhere it doesn't expect. Pointing PYTHONHOME at the
interpreter that is running fixes it outright. Setting the variables inside this process is
enough; they do not have to be exported before launch.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RESOLVE_DIR = Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve")
SCRIPT_API = Path(
    r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
)


def connect():
    """Return the Resolve app object, or raise with something actionable."""
    os.environ.setdefault("PYTHONUTF8", "1")
    # sys.prefix is the running interpreter's root, so this stays correct if the venv or
    # the Python version changes.
    os.environ.setdefault("PYTHONHOME", sys.prefix)
    os.environ["RESOLVE_SCRIPT_API"] = str(SCRIPT_API)
    os.environ["RESOLVE_SCRIPT_LIB"] = str(RESOLVE_DIR / "fusionscript.dll")

    modules = str(SCRIPT_API / "Modules")
    if modules not in sys.path:
        sys.path.append(modules)
    os.environ["PYTHONPATH"] = modules

    try:
        import DaVinciResolveScript as dvr
    except Exception as exc:
        raise RuntimeError(
            f"could not load fusionscript ({exc}). Resolve must be running, and this must "
            f"be Resolve Studio - Blackmagic gates external scripting to Studio."
        ) from exc

    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        raise RuntimeError(
            "Resolve is not reachable. Check it is running, and that Preferences > System > "
            "General > 'External scripting using' is set to Local."
        )
    return resolve


def require_writable(timeline) -> None:
    """Fail loudly if Resolve accepted the connection but will not accept writes.

    After Resolve crashes and restarts, the scripting bridge frequently comes back
    half-alive: getters work perfectly - project name, timeline, every clip - while setters
    return None instead of True/False. Scripts then report success having changed nothing,
    which has silently thrown away a whole grade pass more than once.

    A None (rather than False) from a setter is the signature. Restarting Resolve clears it.
    """
    items = timeline.GetItemListInTrack("video", 1) or []
    if not items:
        raise RuntimeError("timeline has no video items to test against")
    probe = items[0].SetCDL({
        "NodeIndex": "1", "Slope": "1 1 1", "Offset": "0 0 0",
        "Power": "1 1 1", "Saturation": "1.0",
    })
    if probe is not True:
        raise RuntimeError(
            f"Resolve is connected but not accepting writes (SetCDL returned {probe!r}). "
            f"This happens after a crash-restart. Quit Resolve fully and reopen it, then "
            f"re-run - retrying against this session will keep silently doing nothing."
        )
