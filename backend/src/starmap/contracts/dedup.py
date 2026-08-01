"""Case-insensitive keying and duplicate detection.

Used by contracts AND kernels, so joins and uniqueness agree everywhere.
"""

from collections.abc import Iterable


def casefold_key(s: str) -> str:
    """Casefold and collapse whitespace runs to single spaces."""
    return " ".join(s.casefold().split())


def find_duplicates(items: Iterable[str]) -> list[str]:
    """First-seen spellings of case-insensitive duplicates, in first-seen order."""
    first_seen: dict[str, str] = {}
    duplicate_keys: set[str] = set()
    duplicates: list[str] = []
    for item in items:
        key = casefold_key(item)
        if key in first_seen:
            if key not in duplicate_keys:
                duplicate_keys.add(key)
                duplicates.append(first_seen[key])
        else:
            first_seen[key] = item
    return duplicates
