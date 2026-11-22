"""F-11 (attack-from-outside review, 22 November 2026): the free texts an administrator writes go in the invitation
email sent by DOMHOUSE (the invited person's name, and the inviter's own name) and in every list of the organisation.
Without a rule an admin of any organisation could send phishing with a link from DOMHOUSE's sender, up to 50 an hour,
and save fields of about 1 MiB. Now a name is at most 80 characters and an address 200 (as platform.py and account.py),
with no control or invisible direction character and nothing that reads as a web address: a scheme («://»), «www.» or
a domain followed by a path («esempio.it/…»). A plain domain alone («Casa.it») stays allowed: names like «M. Rossi»
must pass. Refused: 422, as any field out of its limits."""
import re
from typing import Annotated

from pydantic import AfterValidator, Field

LINK_LIKE = re.compile(r"(?i)(://|\bwww\.|\b[a-z0-9-]+\.[a-z]{2,24}/)")
INVISIBLE = {"​", "‌", "‍", "⁠", "﻿", *map(chr, range(0x202A, 0x202F)),
             *map(chr, range(0x2066, 0x206A))}


def plain(value: str | None) -> str | None:
    if value is None:
        return value
    if any(ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F or c in INVISIBLE for c in value):
        raise ValueError("control or invisible character")
    if LINK_LIKE.search(value):
        raise ValueError("looks like a web address")
    return value


PlainName = Annotated[str, Field(max_length=80), AfterValidator(plain)]
PlainAddress = Annotated[str, Field(max_length=200), AfterValidator(plain)]
