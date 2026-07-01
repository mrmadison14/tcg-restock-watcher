from __future__ import annotations
import re
from difflib import SequenceMatcher

_STRIP_WORDS = (
    "pokémon", "pokemon", "one piece",
    "dragon ball super", "dragon ball", "fusion world",
    "english", "japanese",
)


def normalize(title: str) -> str:
    s = title.lower()
    s = re.sub(r"\betb\b", "elite trainer box", s)
    for w in _STRIP_WORDS:
        s = s.replace(w, " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def best_match(norm_title: str, index: dict, threshold: float):
    q = set(norm_title.split())
    if not q:
        return None
    best = None
    best_ratio = 0.0
    for name, entry in index.items():
        ratio = SequenceMatcher(None, norm_title, name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = (name, entry)
    if best is None or best_ratio < threshold:
        return None
    name, entry = best
    if not (q & set(name.split())):
        return None
    return (entry["display_name"], entry["market_usd"])
