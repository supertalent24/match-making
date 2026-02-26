import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def remote_ui():
    script = PROJECT_ROOT / "scripts" / "dagster-remote-ui.sh"
    os.execvp("bash", ["bash", str(script)] + sys.argv[1:])


def local_dev():
    os.chdir(PROJECT_ROOT)
    os.environ.setdefault("DAGSTER_HOME", str(PROJECT_ROOT))
    os.execvp(
        sys.executable,
        [sys.executable, "-m", "dagster", "dev", "-m", "talent_matching.definitions"]
        + sys.argv[1:],
    )
