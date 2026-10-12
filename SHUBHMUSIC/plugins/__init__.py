"""Every module in this package that defines register(ctx) is loaded automatically."""

import importlib
import pkgutil


def register_all(ctx) -> None:
    for info in pkgutil.walk_packages(__path__, __name__ + "."):
        if info.ispkg:
            continue
        module = importlib.import_module(info.name)
        fn = getattr(module, "register", None)
        if fn is not None:
            fn(ctx)
