"""Точка входа собранной программы (redfront.exe, PyInstaller): без аргументов - окно кампании в браузере,
с аргументами - как python -m redfront (new, build, menu...)."""
import sys

from redfront.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["gui"]))
