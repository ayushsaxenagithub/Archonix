"""Allow ``python -m archonix``."""

import sys

from .cli import main

sys.exit(main())
