"""Guards the Windows cp1252 trap — non-ASCII must round-trip under UTF-8.

This test matters because Python's default text encoding on Windows is cp1252,
not UTF-8. A stray em-dash in a research question, written without an explicit
encoding, would either crash or corrupt silently.
"""

from __future__ import annotations

from pathlib import Path

from latris.repo.yaml_io import dump_model, load_model
from latris.schema import DescriptionEntry, DescriptionSet, HumanActor, Informants


def test_emdash_and_unicode_round_trip(tmp_path: Path) -> None:
    payload = DescriptionSet(
        entries=[
            DescriptionEntry(
                target_id="node_01HZZZZZZZZZZZZZZZZZZZZZZZ",
                value="Price — the posted retail price (€ denominated). 测试 🎯",
                informants=Informants(proposed_by=[HumanActor(name="Ångström, Ørjan")]),
            ),
        ]
    )
    path = tmp_path / "descriptions.yaml"
    dump_model(payload, path)

    raw = path.read_bytes().decode("utf-8")
    assert "—" in raw
    assert "€" in raw
    assert "测试" in raw
    assert "🎯" in raw
    assert "Ångström" in raw

    loaded = load_model(DescriptionSet, path)
    assert loaded == payload


def test_file_is_lf_terminated(tmp_path: Path) -> None:
    payload = DescriptionSet(
        entries=[
            DescriptionEntry(target_id="node_01HZZZZZZZZZZZZZZZZZZZZZZZ", value="hello"),
        ]
    )
    path = tmp_path / "descriptions.yaml"
    dump_model(payload, path)
    raw = path.read_bytes()
    # No CRLF anywhere — .gitattributes wants LF on disk regardless of OS.
    assert b"\r\n" not in raw
    # File ends with exactly one LF.
    assert raw.endswith(b"\n")
