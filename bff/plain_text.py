"""F-11 (attack-from-outside review, 22 November 2026): the free texts an administrator writes (people's names, the
apartment's address) have a length and no invisible or control character. A name is at most 80 characters and an
address 200 (as platform.py and account.py). Refused: 422 invalid_text with the field and an Italian sentence (a6,
22 November; bff/main.py turns the validation error into that answer; the apartment's address is checked in its route,
only when it changes, rereading B-4).

Answer 1246 (the committente, 22 November 2026): the app's emails carry no user-written text at all (bff/invites.py,
bff/deletion.py, tests/email_no_user_text_test.py), so the rule «looks like a web address» is gone: «M. Rossi»,
«Dott.ssa Bianchi», «Via S.Maria/3» or a text with a link are names and addresses like any other.

The characters (rereading B-3): the text is brought to NFKC, then refused by Unicode category: control (Cc), format (Cf:
direction marks, soft hyphen, tags), line and paragraph separators (Zl, Zp), private use (Co), unassigned (Cn),
surrogates (Cs), and the blank fillers."""
import unicodedata
from typing import Annotated

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

REFUSED_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Co", "Cn", "Cs"}
BLANK_FILLERS = {"ᅟ", "ᅠ", "ㅤ", "ﾠ", "⠀"}
ERROR = "invalid_text"


def _rule(subject: str, longest: int):
    """subject: «Il nome» or «L'indirizzo», the start of each sentence."""
    def check(value: str | None) -> str | None:
        if value is None:
            return value
        if len(value) > longest:
            raise PydanticCustomError(ERROR, f"{subject} può avere al massimo {longest} caratteri.")
        text = unicodedata.normalize("NFKC", value)
        if any(unicodedata.category(c) in REFUSED_CATEGORIES or c in BLANK_FILLERS for c in value + text):
            raise PydanticCustomError(ERROR, f"{subject} contiene caratteri non ammessi.")
        return value
    return check


_name_rule = _rule("Il nome", 80)
_address_rule = _rule("L'indirizzo", 200)
PlainName = Annotated[str, AfterValidator(_name_rule)]
PlainAddress = Annotated[str, AfterValidator(_address_rule)]


def acceptable_name(value: str) -> bool:
    """Rereading B-11: whether a name taken from elsewhere (a token's «name» claim) follows the rule."""
    try:
        _name_rule(value)
    except PydanticCustomError:
        return False
    return True


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
