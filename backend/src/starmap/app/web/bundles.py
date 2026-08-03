"""Agreement-bundle assembly for the composition root (doc 01, "Files").

Moved from `backend/scripts/evaluate_student.py` so the web app and the CLI
share one assembly; `app` is the composition root and may import `assist` and
`transfer`. An unknown major key raises the typed 409 precondition instead of
the script's old `ValueError`, with the same message.
"""

from starmap.app.web.errors import UnknownAgreementError
from starmap.assist.store import ArticulationStore
from starmap.transfer.evaluate import AgreementBundle, DeptAgreement


def load_bundle(
    store: ArticulationStore, sending: int, receiving: int, major_key: str
) -> AgreementBundle:
    agreements = store.load_agreements_for_pair(sending, receiving)
    majors = [item for item in agreements if item.assist_key == major_key]
    if not majors:
        raise UnknownAgreementError(sending, receiving, major_key)
    major = majors[0]
    latest_year_id = store.latest_year_for_pair(sending, receiving)
    assert latest_year_id is not None  # the pair has at least the major agreement
    labels = {year.year_id: year.label for year in store.load_academic_years()}
    return AgreementBundle(
        major=major,
        major_articulations=tuple(store.load_articulations(major.agreement_id)),
        requirement_groups=tuple(store.load_requirements(major.agreement_id)),
        dept_agreements=tuple(
            DeptAgreement(
                agreement=item,
                articulations=tuple(store.load_articulations(item.agreement_id)),
            )
            for item in agreements
            if item.category == "dept"
        ),
        latest_year_id=latest_year_id,
        latest_year_label=labels[latest_year_id],
    )
