import re

_ASCII_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_REPEATED = re.compile(r"(.)\1{2,}")
_WHITESPACE = re.compile(r"\s+")

def turkish_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def collapse_repeats(text: str) -> str:
    return _REPEATED.sub(r"\1\1", text)


def fold_ascii(text: str) -> str:
    return text.translate(_ASCII_MAP)


def normalize(text: str) -> str:
    text = collapse_repeats(text.strip())
    text = _WHITESPACE.sub(" ", text)
    return turkish_lower(text)