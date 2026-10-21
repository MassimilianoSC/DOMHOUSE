"""What the engine does about humidity in an empty apartment (rule mold_protection, R3 of P-60 step 5, D-126).

PLACEHOLDER. Today the engine only warns: above the threshold (65 % by default, 50–80) with the apartment in "empty",
one decision a day, no automatic action. The climate in "dry" mode as an automatic action is an option per apartment
after the pilot:
- what is missing: the choice, per apartment, to let the engine dry the air (how long, how often), and the results
  of the pilot on how damp the apartments really get;
- who decides: the client (Massimiliano), with the managers of the pilot apartments;
- by when: after the pilot.
Only this module changes then; engine/core.py asks it what to do and logs the warning itself.
"""


def mold_action(apartment_mode: str, humidity_percent: float, threshold: float) -> dict | None:
    """The command to run against the humidity, or None. Placeholder: always None (warning only)."""
    return None
