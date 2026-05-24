#!/usr/bin/env python3
"""Clawdmeter daemon entry script.

Thin shim that delegates to the package CLI. Kept as a top-level script so
existing systemd / launchd unit files can keep pointing at a single path
even if we further split the package internals.
"""

import sys

from clawdmeter_daemon.cli import main

if __name__ == "__main__":
    sys.exit(main())
