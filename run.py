#!/usr/bin/env python3
"""Raccourci : python run.py  ==  python manage.py serve"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.http import serve

if __name__ == "__main__":
    serve()
