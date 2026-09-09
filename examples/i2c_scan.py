#!/usr/bin/env python3
"""List devices on the Whisplay I2C bus."""

from whisplay_grove.cli import main

raise SystemExit(main(["scan", "--bus", "1"]))

