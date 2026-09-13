"""Builds tiny CCP-shaped SDE archives in memory. Ids are real: Rifter 587, Frigate 25, Ship 6."""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

BUILD = 3503375
RELEASE = "2026-09-10T11:09:04Z"


def encode_pairs(value: Any) -> Any:
    """Inverse of jsonl.decode_pairs: int-keyed dicts become CCP's `_key`/`_value` lists."""
    if isinstance(value, dict):
        if value and all(isinstance(k, int) for k in value):
            out = []
            for k, v in value.items():
                encoded = encode_pairs(v)
                # CCP inlines object values; anything else (including an int-keyed map,
                # which encodes to a list) goes under _value.
                if isinstance(encoded, dict):
                    out.append({"_key": k, **encoded})
                else:
                    out.append({"_key": k, "_value": encoded})
            return out
        return {k: encode_pairs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [encode_pairs(v) for v in value]
    return value


def names(en: str) -> dict:
    return {"de": en, "en": en, "fr": en, "ja": en, "ko": en, "ru": en, "zh": en, "es": en}


def tiny_records() -> dict[str, dict[int, dict]]:
    return {
        "categories": {
            6: {"name": names("Ship"), "published": True},
            7: {"name": names("Module"), "published": True},
            99: {"name": names("Station"), "published": False},
        },
        "groups": {
            25: {
                "categoryID": 6,
                "name": names("Frigate"),
                "published": True,
                "anchorable": False,
                "anchored": False,
                "fittableNonSingleton": False,
                "useBasePrice": False,
            },
            28: {"categoryID": 6, "name": names("Hauler"), "published": True},
            60: {"categoryID": 7, "name": names("Precursor Weapon"), "published": True},
            500: {"categoryID": 99, "name": names("Station Services"), "published": True},
        },
        "metaGroups": {
            1: {"name": names("Tech I")},
            2: {"name": names("Tech II"), "iconID": 24150, "iconSuffix": "t2"},
        },
        "factions": {
            500002: {
                "name": names("Minmatar Republic"),
                "corporationID": 1000051,
                "memberRaces": [2],
            }
        },
        "races": {1: {"name": names("Caldari")}, 2: {"name": names("Minmatar")}},
        "types": {
            587: {
                "groupID": 25,
                "name": names("Rifter"),
                "published": True,
                "portionSize": 1,
                "factionID": 500002,
                "metaGroupID": 1,
                "raceID": 2,
                "techLevel": 1,
                "metaLevel": 0,
                "mass": 1067000.0,
                "volume": 27289.0,
                "packagedVolume": 2500.0,
                "capacity": 140.0,
                "basePrice": 400000.0,
                "marketGroupID": 64,
                "graphicID": 46,
            },
            648: {
                "groupID": 28,
                "name": names("Badger"),
                "published": True,
                "portionSize": 1,
                "raceID": 1,
            },
            600: {
                "groupID": 25,
                "name": names("Odd Frigate"),
                "published": True,
                "portionSize": 1,
                "factionID": 999,
            },
            999999: {
                "groupID": 25,
                "name": names("Unpublished Thing"),
                "published": False,
                "portionSize": 1,
            },
            3000: {
                "groupID": 500,
                "name": names("Station thing"),
                "published": True,
                "portionSize": 1,
            },
        },
        "typeBonus": {
            587: {
                "types": {
                    3329: [
                        {"bonus": 7.5, "bonusText": names("bonus to rate of fire"), "importance": 1}
                    ]
                }
            },
        },
    }


def make_sde_zip(
    records: dict[str, dict[int, dict]], build: int | None = BUILD, release: str | None = RELEASE
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file, rows in records.items():
            lines = [
                json.dumps({"_key": k, **encode_pairs(v)}, ensure_ascii=False)
                for k, v in rows.items()
            ]
            zf.writestr(f"{file}.jsonl", "\n".join(lines) + "\n")
        if build is not None:
            info = {"_key": "sde", "buildNumber": build}
            if release:
                info["releaseDate"] = release
            zf.writestr("_sde.jsonl", json.dumps(info) + "\n")
    return buf.getvalue()


@pytest.fixture
def sde_dir(settings, tmp_path) -> Path:
    settings.INSTANCE_DIR = tmp_path / "instance"
    settings.SDE_DIR = settings.INSTANCE_DIR / "sde"
    return settings.SDE_DIR


@pytest.fixture
def tiny_zip(tmp_path, sde_dir) -> Path:
    path = tmp_path / f"eve-online-static-data-{BUILD}-jsonl.zip"
    path.write_bytes(make_sde_zip(tiny_records()))
    return path
