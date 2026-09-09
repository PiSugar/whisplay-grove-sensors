#!/usr/bin/env python3
"""Continuously print decoded GPS v1.1 fix state."""

from whisplay_grove.cli import main

raise SystemExit(main(["demo", "gps-v11", "--port", "/dev/serial0"]))

