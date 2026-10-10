# Allow python3 -m ignoredrift to run the tool.
import sys

from .cli import main

sys.exit(main())
