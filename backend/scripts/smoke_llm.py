"""The live LLM smoke script (doc 03): the manual gate for both nodes.

User-gated: it refuses to run without ANTHROPIC_API_KEY set and prints what it
will call before doing it. Nothing in `make check`, CI, or tests executes this
file; the user runs it themselves as the live rehearsal for deploy.

Flow: parse the curated demo paste against the committed corpus, build a demo
evaluation from the resolved chips, draft a petition over its at-risk and
no-articulation findings, and print both results with per-run cost totals from
the call log (written to a throwaway temp database).
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

from starmap.app.web.bundles import load_bundle
from starmap.app.web.routes import chip_resolver
from starmap.assist.store import ArticulationStore
from starmap.common.clock import SystemClock
from starmap.common.ids import UuidIdGenerator
from starmap.common.sqlite import SqliteDatabase
from starmap.contracts.petition import PetitionDraft
from starmap.contracts.transcript_parse import TranscriptProposal
from starmap.llm.call_log import SqliteCallLogStore
from starmap.llm.engine import AdapterConfig, GenerationEngine
from starmap.llm.petition_writer import (
    PETITION_WRITER_CONFIG,
    SELECTABLE_BUCKETS,
    write_petition,
)
from starmap.llm.transcript_parser import TRANSCRIPT_PARSER_CONFIG, parse_transcript
from starmap.llm.transport_anthropic import AnthropicTransport, build_client
from starmap.retrieval.index import CourseIndex
from starmap.transfer.evaluate import CourseRequest, build_evaluation

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTICULATION_DB = REPO_ROOT / "data" / "articulation.db"
DEFAULT_CORPUS_DB = REPO_ROOT / "data" / "corpus.db"
DEFAULT_PASTE = REPO_ROOT / "data" / "curated" / "demo_students" / "deanza_ucsd_cs_paste.txt"


def announce(node: str, config: AdapterConfig) -> None:
    print(
        f"  {node}: model {config.model_name}, prompt {config.prompt_version}, "
        f"max_tokens {config.max_tokens}, up to "
        f"{(config.max_repair_attempts + 1) * (config.max_sdk_retries + 1)} provider calls"
    )


def print_run_cost(call_log: SqliteCallLogStore, run_id: str) -> None:
    rows = call_log.list_for_run(run_id)
    total = sum(row.cost_estimate_usd for row in rows)
    tokens_in = sum(row.input_tokens for row in rows)
    tokens_out = sum(row.output_tokens for row in rows)
    print(
        f"  {run_id}: {len(rows)} provider call(s), {tokens_in} in / {tokens_out} out tokens, "
        f"estimated ${total:.4f}"
    )


def run(
    articulation_db: Path,
    corpus_db: Path,
    paste_path: Path,
    sending: int,
    receiving: int,
    major_key: str,
) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; refusing to run live calls.", file=sys.stderr)
        return 2

    text = paste_path.read_text(encoding="utf-8")
    print("About to make LIVE Anthropic calls:")
    announce("transcript_parser", TRANSCRIPT_PARSER_CONFIG)
    announce("petition_writer", PETITION_WRITER_CONFIG)
    print(f"  paste: {paste_path} ({len(text)} chars); pair {sending} -> {receiving}")
    print(f"  major key: {major_key}")
    print()

    clock = SystemClock()
    ids = UuidIdGenerator()
    transport = AnthropicTransport(build_client())
    store = ArticulationStore(SqliteDatabase(articulation_db))
    index = CourseIndex(SqliteDatabase(corpus_db))

    with tempfile.TemporaryDirectory(prefix="smoke_llm_") as tmp:
        call_log = SqliteCallLogStore(SqliteDatabase(Path(tmp) / "smoke_sessions.db"))

        parse_engine: GenerationEngine[TranscriptProposal] = GenerationEngine(
            "transcript_parser",
            TranscriptProposal,
            TRANSCRIPT_PARSER_CONFIG,
            transport,
            call_log,
            clock,
            ids,
        )
        parse_id = ids.new_id("parse")
        parse = parse_transcript(
            parse_id=parse_id,
            sending_institution_id=sending,
            text=text,
            resolver=chip_resolver(index, sending),
            engine=parse_engine,
            clock=clock,
        )
        print(f"Transcript parse: {parse.status}", end="")
        print("" if parse.reason_code is None else f" ({parse.reason_code.value})")
        for chip in parse.chips:
            print(f"  chip [{chip.resolution}] {chip.course_code}: {chip.title}")
        for entry in parse.unresolved:
            print(f"  unresolved: {entry.proposed_code!r} / {entry.proposed_title!r}")
        print_run_cost(call_log, parse_id)
        if parse.status != "succeeded" or not parse.chips:
            print("parse produced no chips; stopping before the petition step", file=sys.stderr)
            return 1
        print()

        bundle = load_bundle(store, sending, receiving, major_key)
        evaluation = build_evaluation(
            requests=[
                CourseRequest(course_code=chip.course_code, units=chip.units_min, title=chip.title)
                for chip in parse.chips
            ],
            vocabulary=frozenset(course.course_code for course in store.load_cc_courses(sending)),
            bundle=bundle,
            id_generator=ids,
            clock=clock,
        )
        positions = [
            position
            for position, finding in enumerate(evaluation.findings)
            if finding.bucket in SELECTABLE_BUCKETS
        ]
        if not positions:
            print("the evaluation has no petitionable findings; nothing to draft")
            return 0
        names = {
            institution.assist_id: institution.name for institution in store.load_institutions()
        }

        petition_engine: GenerationEngine[PetitionDraft] = GenerationEngine(
            "petition_writer",
            PetitionDraft,
            PETITION_WRITER_CONFIG,
            transport,
            call_log,
            clock,
            ids,
        )
        petition_id = ids.new_id("pet")
        petition = write_petition(
            petition_id=petition_id,
            evaluation=evaluation,
            finding_positions=positions,
            sending_name=names[sending],
            receiving_name=names[receiving],
            major_label=bundle.major.label,
            engine=petition_engine,
            clock=clock,
        )
        print(f"Petition: {petition.status} (fallback: {petition.fallback})", end="")
        print("" if petition.reason_code is None else f" ({petition.reason_code.value})")
        if petition.letter_text is not None:
            print()
            print(petition.letter_text)
            print()
            print(f"  cited: {[entry.course_code for entry in petition.cited]}")
        print_run_cost(call_log, petition_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live LLM smoke run over the committed artifacts.")
    parser.add_argument("--db", type=Path, default=DEFAULT_ARTICULATION_DB, help="artifact path")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_DB, help="corpus path")
    parser.add_argument("--paste", type=Path, default=DEFAULT_PASTE, help="demo paste text file")
    parser.add_argument("--sending", type=int, default=113, help="sending institution id")
    parser.add_argument("--receiving", type=int, default=7, help="receiving institution id")
    parser.add_argument("--major-key", required=True, help="assist key of the major agreement")
    arguments = parser.parse_args(argv)

    for path, hint in (
        (arguments.db, "run `make unpack-data`"),
        (arguments.corpus, "run `make unpack-data`"),
        (arguments.paste, "check the curated demo files"),
    ):
        if not path.exists():
            parser.error(f"{path} does not exist ({hint})")

    return run(
        articulation_db=arguments.db,
        corpus_db=arguments.corpus,
        paste_path=arguments.paste,
        sending=arguments.sending,
        receiving=arguments.receiving,
        major_key=arguments.major_key,
    )


if __name__ == "__main__":
    sys.exit(main())
