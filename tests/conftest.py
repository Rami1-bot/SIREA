# tests/conftest.py
"""Ajustes comunes: las pruebas usan las skills del repositorio salvo que activen las versiones aprendidas."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SIREA_SKILLS_SOLO_REPOSITORIO", "1")


@pytest.fixture(autouse=True)
def _cache_de_skills_limpia():
    from src.agentes import skills
    skills.invalidar_cache()
    yield
    skills.invalidar_cache()
