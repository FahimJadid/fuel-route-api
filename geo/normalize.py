import re
import unicodedata

_NON_ALNUM = re.compile(r"[^A-Za-z0-9 ]")
_ABBREVIATED_PREFIXES = (("MC ", "MC"), ("ST ", "SAINT "), ("FT ", "FORT "), ("MT ", "MOUNT "))

# Census Gazetteer NAME carries the legal/statistical descriptor; LSAD says which one.
_LSAD_SUFFIXES = {
    "21": " borough",
    "25": " city",
    "37": " municipality",
    "43": " town",
    "47": " village",
    "53": " city and borough",
    "55": " comunidad",
    "57": " CDP",
    "62": " zona urbana",
}
_GOVERNMENT_DESCRIPTORS = (
    " (balance)",
    " unified government",
    " consolidated government",
    " metropolitan government",
    " urban county",
    " corporation",
    " city",
)


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("'", "").replace("’", "")
    text = _NON_ALNUM.sub(" ", text).upper()
    text = " ".join(text.split())
    for prefix, replacement in _ABBREVIATED_PREFIXES:
        if text.startswith(prefix):
            return replacement + text[len(prefix) :]
    return text


def name_key(name: str) -> str:
    return normalize_name(name).replace(" ", "")


def strip_gazetteer_suffix(name: str, lsad: str) -> str:
    suffix = _LSAD_SUFFIXES.get(lsad)
    if suffix is not None:
        return name.removesuffix(suffix)
    for descriptor in _GOVERNMENT_DESCRIPTORS:
        name = name.removesuffix(descriptor)
    return name
