from __future__ import annotations

import subprocess
import sys


def test_lemma1_symbolic_verification_script() -> None:
    proc = subprocess.run(
        [sys.executable, "derivations/examples/lemma1_check.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "passed" in proc.stdout.lower()
