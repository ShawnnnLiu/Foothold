from starmap.contracts.dedup import casefold_key, find_duplicates


def test_casefold_key_casefolds_and_collapses_whitespace() -> None:
    assert casefold_key("  John   SMITH ") == "john smith"
    assert casefold_key("Straße") == casefold_key("STRASSE")


def test_find_duplicates_empty_when_unique() -> None:
    assert find_duplicates(["Ada Lovelace", "Grace Hopper"]) == []


def test_find_duplicates_returns_first_seen_spellings() -> None:
    items = ["John Smith", "Jane Doe", "john  smith", "JANE DOE", "john smith"]
    assert find_duplicates(items) == ["John Smith", "Jane Doe"]
