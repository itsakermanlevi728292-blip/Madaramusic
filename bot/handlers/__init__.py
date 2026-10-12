from . import controls, events, owner, play, playlist, search, settings, start


def register_all(ctx) -> None:
    for module in (start, play, controls, playlist, search, settings, owner, events):
        module.register(ctx)
