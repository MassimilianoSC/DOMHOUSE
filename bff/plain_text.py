"""F-11 (attack-from-outside review, 22 November 2026): the free texts an administrator writes go in the invitation
email sent by DOMHOUSE (the invited person's name, and the inviter's own name) and in every list of the organisation.
Without a rule an admin of any organisation could send phishing with a link from DOMHOUSE's sender, up to 50 an hour,
and save fields of about 1 MiB. Now a name is at most 80 characters and an address 200 (as platform.py and account.py).
Refused: 422 invalid_text with the field and an Italian sentence (a6, 22 November; bff/main.py turns the validation
error into that answer; the apartment's address is checked in its route, only when it changes, rereading B-4).

The rule (rereading of the low fixes, B-3): the text is first brought to NFKC (full-width «：／．» become «:/.»), and the
ideographic full stops become «.»; then
- refused characters by Unicode category: control (Cc), format (Cf: direction marks, soft hyphen, tags), line and
  paragraph separators (Zl, Zp), private use (Co), unassigned (Cn), surrogates (Cs), and the blank fillers;
- refused everywhere: a scheme («://», «mailto:», «javascript:»…), «//», «www.», an IPv4 address, and a domain followed
  by a path, a query, a port or a backslash («esempio.it/…», «evil.com:8080»), labels in any script (homoglyphs);
- in a name also a domain alone with a common top-level domain («Casa.it», «evil-domhouse.com»): Gmail and Outlook make
  it a link in the invitation email; an address may name one. A label has at least 2 characters before its dot and an
  abbreviation is not a domain, so «M. Rossi», «Dott.ssa Bianchi», «S.r.l.» and «Via S.Maria/3» pass."""
import re
import unicodedata
from typing import Annotated

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

REFUSED_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Co", "Cn", "Cs"}
BLANK_FILLERS = {"ᅟ", "ᅠ", "ㅤ", "ﾠ", "⠀"}
FULL_STOPS = str.maketrans({"。": ".", "｡": ".", "︒": "."})
LINK_ANYWHERE = re.compile(
    r"(?i)(://|//|\bwww\.|\b(?:mailto|https?|ftp|file|javascript|data|tel|sms|ws|wss):"
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b"
    r"|[\w-]{2,}\.[^\W\d_]{2,24}(?=[/?#:\\]))")
TOP_LEVEL = ("com|net|org|info|biz|xyz|top|app|dev|online|site|shop|store|link|click|live|tech|club|website|page|"
             "cloud|email|login|support|help|services|digital|network|today|news|world|life|vip|win|bid|loan|work")
DOMAIN_ALONE = re.compile(rf"(?i)[\w-]{{2,}}\.(?:[a-z]{{2}}|{TOP_LEVEL})\b")
ERROR = "invalid_text"


def _normal(value: str) -> str:
    return unicodedata.normalize("NFKC", value).translate(FULL_STOPS)


def _rule(subject: str, longest: int, domain_alone: bool):
    """subject: «Il nome» or «L'indirizzo», the start of each sentence; domain_alone: a bare domain is refused too."""
    def check(value: str | None) -> str | None:
        if value is None:
            return value
        if len(value) > longest:
            raise PydanticCustomError(ERROR, f"{subject} può avere al massimo {longest} caratteri.")
        text = _normal(value)
        if any(unicodedata.category(c) in REFUSED_CATEGORIES or c in BLANK_FILLERS for c in value + text):
            raise PydanticCustomError(ERROR, f"{subject} contiene caratteri non ammessi.")
        if LINK_ANYWHERE.search(text) or (domain_alone and DOMAIN_ALONE.search(text)):
            raise PydanticCustomError(ERROR, f"{subject} non può contenere un indirizzo web.")
        return value
    return check


_name_rule = _rule("Il nome", 80, domain_alone=True)
_address_rule = _rule("L'indirizzo", 200, domain_alone=False)
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
