# -*- coding: utf-8 -*-
"""Runtime binding for extracted ISHApp feature modules."""
from __future__ import annotations

from types import ModuleType
from typing import Any


def bind_main_globals(main_namespace: dict[str, Any], *feature_modules: ModuleType) -> None:
    shared = {key: value for key, value in main_namespace.items() if not key.startswith('__')}
    for module in feature_modules:
        module.__dict__.update(shared)
