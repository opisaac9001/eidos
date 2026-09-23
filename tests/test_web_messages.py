import shutil
import subprocess
from pathlib import Path

import pytest


def test_incremental_message_nodes_and_unread_state():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the browser-independent DOM-double test")
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [
            node,
            str(root / "tests/web_message_test.cjs"),
            str(root / "src/eidos/adapters/web/app.js"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
