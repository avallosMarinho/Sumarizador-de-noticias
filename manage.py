#!/usr/bin/env python3
"""Interface web local; o CLI original continua disponível em app.py."""
import os
import sys


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "newsroom.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
