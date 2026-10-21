"""What the engine does about humidity in an empty apartment (rule mold_protection, R3 of P-60 step 5, D-126).

PLACEHOLDER. Today the engine only warns: above the threshold (65 % by default, 50–80) with the apartment in "empty",
one decision a day, no automatic action. The climate in "dry" mode as an automatic action is an option per apartment,
unlocked by its condition (D-139, registro section 7; D-138: no "later" without its condition): a decision of the
client, per apartment, after seeing how often the warning fires (with how long and how often to dry the air).
Only this module changes then; engine/core.py asks it what to do and logs the warning itself.
"""


def mold_action(apartment_mode: str, humidity_percent: float, threshold: float) -> dict | None:
    """The command to run against the humidity, or None. Placeholder: always None (warning only)."""
    return None
