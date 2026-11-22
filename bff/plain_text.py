"""F-11 (attack-from-outside review, 22 November 2026): the free texts an administrator writes go in the invitation
email sent by DOMHOUSE (the invited person's name, and the inviter's own name) and in every list of the organisation.
Without a rule an admin of any organisation could send phishing with a link from DOMHOUSE's sender, up to 50 an hour,
and save fields of about 1 MiB. Now a name is at most 80 characters and an address 200 (as platform.py and account.py).
Refused: 422 invalid_text with the field and an Italian sentence (a6, 22 November; bff/main.py turns the validation
error into that answer; the apartment's address is checked in its route, only when it changes, rereading B-4).

The rule (rereadings B-3 and R-1, R-4, R-6): the text is first brought to NFKC (full-width «：／．» become «:/.»), and
the ideographic full stops become «.»; then
- refused characters by Unicode category: control (Cc), format (Cf: direction marks, soft hyphen, tags), line and
  paragraph separators (Zl, Zp), private use (Co), unassigned (Cn), surrogates (Cs), and the blank fillers;
- refused everywhere: a scheme («://», «mailto:», «javascript:»…), «//», «www.», an IPv4 address;
- in a name: any «label.letters» not followed by a letter, in any script (a domain, bare or with a path, also with a
  homoglyph at its end), after the Italian titles and forms are taken out («Sig.ra», «Avv.to», «Spett.le», «Dott.ssa»…);
  and «tel:», «sms:». «M. Rossi», «S.r.l.», «F.lli» pass (a label has at least 2 characters);
- in an address: a domain followed by a path, a query, a port or a backslash only with a known top-level domain
  («Fraz.Colle/2», «Via Sta.Maria/3», «Tel: 06…» are addresses); a bare domain is allowed."""
import re
import unicodedata
from typing import Annotated

from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

REFUSED_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Co", "Cn", "Cs"}
BLANK_FILLERS = {"ᅟ", "ᅠ", "ㅤ", "ﾠ", "⠀"}
FULL_STOPS = str.maketrans({"。": ".", "｡": ".", "︒": "."})
SCHEMES = "mailto|https?|ftp|file|javascript|data|ws|wss"
LINK_ALWAYS = rf"://|//|\bwww\.|\b(?:{SCHEMES}):|\b\d{{1,3}}(?:\.\d{{1,3}}){{3}}\b"
LETTERS = r"[^\W\d_]"                     # letters of any script
# final rereading R-1: Italian titles and forms are «letters.letters» like a domain: taken out before the check
ABBREVIATIONS = re.compile(
    r"(?i)(?<![\w.])(?:sig\.r[aie]|sig\.na|avv\.t[oa]|spett\.l[ei]|ill\.m[oai]|gent\.m[oaie]|egr\.gi[oa]?|coop\.va|"
    r"ass\.ne|dott\.ssa|dott\.re|prof\.ssa|arch\.tt[oa]|ing\.re|rag\.re|geom\.ra|on\.le|ecc\.mo|rev\.mo|mons\.re)"
    rf"(?!{LETTERS})")
# final rereading R-4: in a name any «label.letters» (letters of any script, also a homoglyph at its end) not followed by
# a letter is a domain: a linkifier may make a link of «evil.zip», «evil-dom.house» or «evil.com» in «evil.comа»
NAME_LINK = re.compile(rf"(?i)(?:{LINK_ALWAYS}|\b(?:tel|sms):|[\w-]{{2,}}\.{LETTERS}{{2,}}(?!{LETTERS}))")
# final rereading R-6: in an address a domain with a path only with a known top-level domain («Fraz.Colle/2»,
# «Via Sta.Maria/3», «Loc.Tà/3» are addresses), and no tel:/sms: («Tel: 06…» is a phone number); a bare domain is allowed
TOP_LEVEL = ("com|net|org|info|biz|xyz|top|app|dev|online|site|shop|store|link|click|live|tech|club|website|page|"
             "cloud|email|login|support|help|services|digital|network|today|news|world|life|vip|win|bid|loan|work|zip|"
             "mov|bank|icu|pro|ninja|academy|house|museum|"
             "it|eu|co|io|me|ru|cn|uk|de|fr|es|ch|at|nl|be|us|tv|ly|to|cc|ws|tk|ml|ga|cf|gq|su|in|br|pl|cz|ro|gr|pt|"
             "se|dk|fi|ie|hu|sk|si|hr|rs|bg|ua|by|kz|jp|kr|tw|hk|sg|au|nz|ca|mx|ar|cl|za|ng|ke|ir|tr|il|ae|sa|pk|vn|"
             "th|id|ph|my|gg|sh|ai|gl|im|am|fm|la")
ADDRESS_LINK = re.compile(rf"(?i)(?:{LINK_ALWAYS}|[\w-]{{2,}}\.(?:{TOP_LEVEL})(?!{LETTERS})(?=[/?#:\\]))")
ERROR = "invalid_text"


def _normal(value: str) -> str:
    return unicodedata.normalize("NFKC", value).translate(FULL_STOPS)


def _rule(subject: str, longest: int, links: re.Pattern, titles: bool):
    """subject: «Il nome» or «L'indirizzo», the start of each sentence; links: what reads as a web address there;
    titles: the Italian abbreviations are taken out first (names)."""
    def check(value: str | None) -> str | None:
        if value is None:
            return value
        if len(value) > longest:
            raise PydanticCustomError(ERROR, f"{subject} può avere al massimo {longest} caratteri.")
        text = _normal(value)
        if any(unicodedata.category(c) in REFUSED_CATEGORIES or c in BLANK_FILLERS for c in value + text):
            raise PydanticCustomError(ERROR, f"{subject} contiene caratteri non ammessi.")
        if titles:
            text = ABBREVIATIONS.sub(" ", text)
        if links.search(text):
            raise PydanticCustomError(ERROR, f"{subject} non può contenere un indirizzo web.")
        return value
    return check


_name_rule = _rule("Il nome", 80, NAME_LINK, titles=True)
_address_rule = _rule("L'indirizzo", 200, ADDRESS_LINK, titles=False)
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
