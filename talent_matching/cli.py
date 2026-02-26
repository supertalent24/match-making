import os
import sys
from pathlib import Path


def remote_ui():
    project_root = Path(__file__).resolve().parent.parent
    script = project_root / "scripts" / "dagster-remote-ui.sh"
    os.execvp("bash", ["bash", str(script)] + sys.argv[1:])
