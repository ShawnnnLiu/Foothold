import re

from starmap.common.ids import IdGenerator, UuidIdGenerator, sha256_hex
from tests.support.ids import SequentialIdGenerator


def test_uuid_ids_match_prefix_format() -> None:
    generated = UuidIdGenerator().new_id("course")
    assert re.fullmatch(r"course_[0-9a-f]{16}", generated)


def test_uuid_ids_are_unique() -> None:
    generator = UuidIdGenerator()
    ids = {generator.new_id("x") for _ in range(200)}
    assert len(ids) == 200


def test_sequential_generator_counts_up() -> None:
    generator = SequentialIdGenerator()
    assert generator.new_id("run") == "run_0000000000000001"
    assert generator.new_id("run") == "run_0000000000000002"
    assert generator.new_id("doc") == "doc_0000000000000003"


def test_implementations_satisfy_protocol() -> None:
    assert isinstance(UuidIdGenerator(), IdGenerator)
    assert isinstance(SequentialIdGenerator(), IdGenerator)


def test_sha256_hex_known_vectors() -> None:
    assert sha256_hex("") == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert sha256_hex("abc") == ("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
