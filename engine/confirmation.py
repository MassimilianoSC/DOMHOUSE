"""How the engine confirms a command the device cannot confirm itself (outcome "delivered", connector.md §2.5).

PLACEHOLDER (D-115). Today every "delivered" command is treated as confirmation "none": acked, the app shows the state
requested. The real rule for "confirmation: power" (acked only when the watts of the meter linked by
links.confirmation_device_id move the right way within the 10 s, otherwise timeout with reason no_confirmation)
needs what is not here yet:
- what is missing: a real split behind an infrared blaster and its power meter, linked in the catalog;
- who gives it: Youssouf, with the Shelly connector and its catalog (catalog.yaml, links);
- by when: step 7 of the plan, in week 3 of Youssouf's calendar.
Only this module changes then; engine/core.py asks it and does nothing else about it.
"""


def delivered_outcome(capability_state: dict, links: dict[str, str] | None = None) -> str:
    """The command's final status when the connector answered "delivered". Placeholder: always "acked"."""
    return "acked"
