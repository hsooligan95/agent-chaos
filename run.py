#!/usr/bin/env python3
"""Run AgentChaos without installing: ``python run.py run``.

Equivalent to ``python -m agentchaos run`` after ``pip install -e .``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agentchaos.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
