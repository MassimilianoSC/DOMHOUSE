"""F-11 (attack-from-outside review, 22 November 2026): the free texts an administrator writes go in the invitation
email sent by DOMHOUSE (the invited person's name, and the inviter's own name) and in every list of the organisation.
Without a rule an admin of any organisation could send phishing with a link from DOMHOUSE's sender, up to 50 an hour,
and save fields of about 1 MiB. Now a name is at most 80 characters and an address 200 (as platform.py and account.py),
with no control or invisible direction character and nothing that reads as a web address: a scheme («://»), «www.» or
a domain followed by a path («esempio.it/…»). A plain domain alone («Casa.it») stays allowed: names like «M. Rossi»
must pass. Refused: 422 invalid_text with the field and an Italian sentence (a6, 22 November; bff/main.py turns the
validation error into that answer)."""
import re
from typing import Annotated

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

# rereading B-4: a domain's label has at least 2 characters, so «Via S.Maria/3» is an address, not a link
LINK_LIKE = re.compile(r"(?i)(://|\bwww\.|\b[a-z0-9-]{2,}\.[a-z]{2,24}/)")
INVISIBLE = {"​", "‌", "‍", "⁠", "﻿", *map(chr, range(0x202A, 0x202F)),
             *map(chr, range(0x2066, 0x206A))}
ERROR = "invalid_text"


def _rule(subject: str, longest: int):
    """subject: «Il nome» or «L'indirizzo», the start of each sentence."""
    def check(value: str | None) -> str | None:
        if value is None:
            return value
        if len(value) > longest:
            raise PydanticCustomError(ERROR, f"{subject} può avere al massimo {longest} caratteri.")
        if any(ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F or c in INVISIBLE for c in value):
            raise PydanticCustomError(ERROR, f"{subject} contiene caratteri non ammessi.")
        if LINK_LIKE.search(value):
            raise PydanticCustomError(ERROR, f"{subject} non può contenere un indirizzo web.")
        return value
    return check


PlainName = Annotated[str, AfterValidator(_rule("Il nome", 80))]
PlainAddress = Annotated[str, AfterValidator(_rule("L'indirizzo", 200))]
_address_rule = _rule("L'indirizzo", 200)


def address_problem(value: str) -> dict | None:
    """Rereading B-4: the address is checked in the route, and only when it changes: the site's form always sends it,
    and one saved before F-11 and now out of the rule must not block every save (A6's switch-off included)."""
    try:
        _address_rule(value)
    except PydanticCustomError as exc:
        return {"error": ERROR, "field": "address", "message": str(exc)}
    return None


def invalid_text(errors: list[dict]) -> dict | None:
    """The answer for the first error of these rules among a request's validation errors; None when there is none."""
    for e in errors:
        if e.get("type") == ERROR:
            field = next((part for part in reversed(e.get("loc", ())) if isinstance(part, str)), "")
            return {"error": ERROR, "field": field, "message": e.get("msg", "")}
    return None
