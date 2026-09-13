import os
import time

import pytest

from apps.sde import incoming
from apps.sde.models import EveType, SdeBuild

from .conftest import BUILD, make_sde_zip, tiny_records

pytestmark = pytest.mark.django_db


def settle(path):
    old = time.time() - 3600
    os.utime(path, (old, old))


def test_fresh_zip_waits_then_imports(sde_dir):
    dirs = incoming.sde_dirs()
    path = dirs["incoming"] / f"eve-online-static-data-{BUILD}-jsonl.zip"
    path.write_bytes(make_sde_zip(tiny_records()))
    assert incoming.scan_incoming() == []  # still settling
    settle(path)
    reports = incoming.scan_incoming()
    assert len(reports) == 1 and reports[0].ok
    assert not path.exists() and (dirs["archive"] / path.name).exists()
    build = SdeBuild.latest()
    assert build is not None and build.build == BUILD
    assert EveType.objects.filter(pk=587).exists()
    assert incoming.scan_incoming() == []


def test_broken_zip_goes_to_failed_with_note(sde_dir):
    dirs = incoming.sde_dirs()
    path = dirs["incoming"] / "mystery.zip"
    path.write_bytes(make_sde_zip({"races": tiny_records()["races"]}, build=None))  # no build info
    settle(path)
    reports = incoming.scan_incoming()
    assert len(reports) == 1 and not reports[0].ok
    moved = dirs["failed"] / "mystery.zip"
    assert moved.exists()
    note = moved.with_suffix(".zip.error.txt").read_text()
    assert "cannot determine the SDE build" in note and "--build" in note


def test_non_zip_files_ignored(sde_dir):
    dirs = incoming.sde_dirs()
    junk = dirs["incoming"] / "notes.txt"
    junk.write_text("hi")
    partial = dirs["incoming"] / "half.zip"
    partial.write_bytes(b"PK\x03\x04 truncated")
    settle(junk)
    settle(partial)
    assert incoming.scan_incoming() == []
    assert partial.exists()


def test_archive_name_collision_gets_suffix(sde_dir):
    dirs = incoming.sde_dirs()
    (dirs["archive"] / "a.zip").write_bytes(b"old")
    src = dirs["incoming"] / "a.zip"
    src.write_bytes(b"new")
    moved = incoming.move_to(src, dirs["archive"])
    assert moved.name.startswith("a-") and moved.suffix == ".zip"
