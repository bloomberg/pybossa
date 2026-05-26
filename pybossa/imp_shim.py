"""Shim for the removed 'imp' module (Python 3.12+).

Provides minimal imp API surface needed by nose and boto.
Must be installed into sys.modules before those packages are imported.
"""
import importlib
import importlib.util
import os
import types

C_EXTENSION = 3
PKG_DIRECTORY = 5
PY_SOURCE = 1

def find_module(name, path=None):
    try:
        if path:
            for dir_ in path:
                full = os.path.join(dir_, name + '.py')
                if os.path.exists(full):
                    return (open(full), full, ('.py', 'r', PY_SOURCE))
                full = os.path.join(dir_, name)
                if os.path.isdir(full) and os.path.exists(os.path.join(full, '__init__.py')):
                    return (None, full, ('', '', PKG_DIRECTORY))
        spec = importlib.util.find_spec(name)
        if spec and spec.origin:
            return (open(spec.origin), spec.origin, ('.py', 'r', PY_SOURCE))
    except (ImportError, ValueError, AttributeError):
        pass
    raise ImportError(f"No module named {name!r}")


def load_module(name, file, filename, details):
    try:
        if details[2] == PKG_DIRECTORY:
            spec = importlib.util.spec_from_file_location(
                name, os.path.join(filename, '__init__.py'),
                submodule_search_locations=[filename])
        else:
            spec = importlib.util.spec_from_file_location(name, filename)
        if spec:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception:
        pass
    return None


def acquire_lock():
    pass


def release_lock():
    pass


def new_module(name):
    return types.ModuleType(name)
