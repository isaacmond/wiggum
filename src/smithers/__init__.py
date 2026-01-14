"""Smithers - Your loyal PR automation assistant, powered by Claude AI."""

import sys

__version__ = "1.7.0"

# Backwards compatibility for legacy imports that still use the wiggum name.
sys.modules.setdefault("wiggum", sys.modules[__name__])
