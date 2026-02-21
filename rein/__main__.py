"""
Allow running Rein as a module: python -m rein

This replaces the old rein.py entry point.
"""
from rein.cli import main

if __name__ == "__main__":
    main()
