import pytest
from pydantic import ValidationError

from starmap.common.ids import sha256_hex
from starmap.contracts.corpus_document import CorpusDocument
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "corpus_document"))
INVALID = list(iter_fixtures("invalid", "corpus_document"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse_and_ids_derive(case: FixtureCase) -> None:
    document = CorpusDocument.model_validate(case.payload)
    derived = (
        "doc_" + sha256_hex(f"{document.source_url}\n{document.date_collected.isoformat()}")[:16]
    )
    assert document.doc_id == derived


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        CorpusDocument.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_model_is_frozen() -> None:
    document = CorpusDocument.model_validate(VALID[0].payload)
    with pytest.raises(ValidationError):
        document.title = "mutated"


def test_unknown_field_rejected() -> None:
    payload = dict(VALID[0].payload) | {"unexpected_field": 1}
    with pytest.raises(ValidationError, match="unexpected_field"):
        CorpusDocument.model_validate(payload)
