from . import DANGER, SUCCESS, button, markup


def _on(flag: bool):
    return SUCCESS if flag else DANGER


def settings_markup(s: dict):
    """Green = open to everyone / on, red = admins only / off."""
    everyone_play, everyone_ctl, clean = s["play_mode"] == "everyone", s["control_mode"] == "everyone", s["clean_commands"]
    return markup([
        [button(f"🎵 Who can play: {'everyone' if everyone_play else 'admins only'}", cb="st:play", style=_on(everyone_play))],
        [button(f"🎛 Who can control: {'everyone' if everyone_ctl else 'admins only'}", cb="st:control", style=_on(everyone_ctl))],
        [button(f"🧹 Delete commands: {'on' if clean else 'off'}", cb="st:clean", style=_on(clean))],
        [button("✖️ Close", cb="st:close", style=DANGER)],
    ])
