"""Точка входа собранной программы (redfront.exe, PyInstaller): без аргументов - окно кампании в браузере,
с аргументами - как python -m redfront (new, build, menu...)."""
import sys

from redfront.__main__ import main

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):      # консоль Windows (cp866/cp1252) не печатает русский - UTF-8, без падений
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:] or ["gui"]))
