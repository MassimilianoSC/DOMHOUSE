"""How the engine confirms a command the device cannot confirm itself (outcome "delivered", connector.md §2.5;
P-60 step 7, D-131).

A split behind an infrared blaster has no feedback: with `confirmation: power` the engine watches the watts of the
meter linked by links.confirmation_device_id. A command that switches the split ON is acked when those watts rise by
at least CONFIRM_ON_WATTS over what they were before the command; one that switches it OFF when they drop under
CONFIRM_OFF_WATTS; both within CONFIRM_UNTIL_S of the command's creation (inside the contract's 10 s). Otherwise the
command ends in timeout, reason no_confirmation. Not verified, acked with the state requested (as `confirmation:
none`): a change that neither switches the split on nor off (setpoint, mode, fan: the watts say nothing reliable in
10 s), a split without a valid link (logged at start, step 7b), and a linked meter offline when the command starts (a
decision says so). The two thresholds are the engine's settings CONFIRM_ON_WATTS and CONFIRM_OFF_WATTS
(engine/config.py), per apartment.
"""
CONFIRM_ON_WATTS = 20.0
CONFIRM_OFF_WATTS = 15.0
CONFIRM_UNTIL_S = 9.5          # from the command's creation: its final status within the contract's 10 s


def switch_direction(before: dict, after: dict) -> str | None:
    """"on" or "off" when the command switches the split; None for any other change (not verified, D-131)."""
    was, will = bool(before.get("on")), bool(after.get("on"))
    if was == will:
        return None
    return "on" if will else "off"


def power_confirms(direction: str, baseline: float, watts: float, on_watts: float, off_watts: float) -> bool:
    """Do these watts confirm the switch? Up by on_watts over the baseline for "on", under off_watts for "off"."""
    if direction == "on":
        return watts >= baseline + on_watts
    return watts < off_watts
