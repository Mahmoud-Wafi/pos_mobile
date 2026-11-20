"""Static audit: every `<x>_service.fn(...)` call in the UI matches the real service signature.

Catches the class of bug where a dialog passes keyword arguments the service does not accept
(e.g. CustomerDialog -> create_customer(name=...), which made 'add customer' fail on every click).
"""
import ast
import importlib
import inspect
import pathlib

SERVICES = {}


def _service(name):
    if name not in SERVICES:
        try:
            SERVICES[name] = importlib.import_module(f"app.services.{name}")
        except ImportError:
            SERVICES[name] = None
    return SERVICES[name]


def _bind_errors():
    errors = []
    for f in sorted(pathlib.Path("app/ui").rglob("*.py")):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id.endswith("_service")):
                continue
            mod = _service(node.func.value.id)
            fn = getattr(mod, node.func.attr, None) if mod else None
            if fn is None:
                if mod is not None:
                    errors.append(f"{f}:{node.lineno} {node.func.value.id}.{node.func.attr} does not exist")
                continue
            if not inspect.isfunction(fn):
                continue
            if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                continue
            try:
                inspect.signature(fn).bind(*[None] * len(node.args), **{k.arg: None for k in node.keywords})
            except TypeError as exc:
                errors.append(f"{f}:{node.lineno} {node.func.attr}: {exc}")
    return errors


def test_ui_calls_match_service_signatures():
    assert _bind_errors() == []
