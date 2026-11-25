#!/usr/bin/env python3
"""Launch the GrokBot switch desktop widget."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from grokbot_switch.app import SwitchApp


def main() -> None:
    app = SwitchApp()
    app.run()


if __name__ == "__main__":
    main()
