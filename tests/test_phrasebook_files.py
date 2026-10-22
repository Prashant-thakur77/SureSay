"""The local phrasebook files are never read half-written, even when a new home is seeded by several requests at once."""

from __future__ import annotations

import threading
from pathlib import Path

from suresay.phrasebook import JsonPhrasebook


def test_concurrent_first_reads_of_a_new_home_never_see_a_partial_file(tmp_path: Path) -> None:
    for round_ in range(30):
        pb = JsonPhrasebook(tmp_path / f"r{round_}")
        errors: list[BaseException] = []

        def read(pb: JsonPhrasebook = pb, errors: list[BaseException] = errors) -> None:
            try:
                assert pb.list("guest-abc")
            except BaseException as e:  # noqa: BLE001 (any failure counts)
                errors.append(e)

        threads = [threading.Thread(target=read) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors[0]


def test_a_write_leaves_no_temporary_files(tmp_path: Path) -> None:
    pb = JsonPhrasebook(tmp_path)
    pb.list("guest-abc")
    pb.add("guest-abc", "my fan", "home_set", {"device": "fan", "state": "on"})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["guest-abc.json"]


def test_adding_to_a_brand_new_home_seeds_it_without_deadlock(tmp_path: Path) -> None:
    pb = JsonPhrasebook(tmp_path)
    t = threading.Thread(target=pb.add, args=("guest-new", "my fan", "home_set", {"device": "fan", "state": "on"}))
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "add() on a new home deadlocked"
    assert any(e["phrase"] == "my fan" for e in pb.list("guest-new"))
