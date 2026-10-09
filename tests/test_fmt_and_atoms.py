"""notion_fmt + atoms — formatting and Atom mapping (Khan parity)."""

from __future__ import annotations

import json

import pytest

from usr.plugins.notion.helpers import atoms, notion_fmt


def _page(pid="p1", title="Doc", props=None):
    return {
        "id": pid,
        "object": "page",
        "properties": props if props is not None else {
            "title": {"type": "title", "title": [{"text": {"content": title}}]}
        },
        "parent": {"type": "workspace"},
        "url": f"https://notion.so/{pid}",
        "last_edited_time": "2026-01-01T00:00:00Z",
    }


def test_extract_title_variants():
    assert notion_fmt.extract_title(_page(title="Hello")) == "Hello"
    # top-level title string (workspace page shape)
    assert notion_fmt.extract_title({"id": "x", "title": "Top"}) == "Top"
    # named title column
    assert notion_fmt.extract_title({
        "id": "x",
        "properties": {"Name": {"type": "title", "title": [{"text": {"content": "Named"}}]}},
    }) == "Named"
    assert notion_fmt.extract_title({"id": "x", "properties": {}}) == "Untitled"


def test_rich_text_flattening():
    rich = [
        {"text": {"content": "Hello "}},
        {"text": {"content": "world"}, "plain_text": "world"},
        {"plain_text": "plain"},
    ]
    assert notion_fmt.rich_text(rich) == "Hello worldplain"


def test_block_to_line_types():
    assert notion_fmt.block_to_line(
        {"type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "H"}}]}}
    ) == "## H"
    assert notion_fmt.block_to_line(
        {"type": "to_do", "to_do": {"checked": True, "rich_text": [{"text": {"content": "t"}}]}}
    ) == "- [x] t"
    assert notion_fmt.block_to_line(
        {"type": "code", "code": {"language": "py", "rich_text": [{"text": {"content": "x=1"}}]}}
    ) == "```py\nx=1\n```"
    assert notion_fmt.block_to_line({"type": "divider", "divider": {}}) == "---"
    assert notion_fmt.block_to_line(
        {"type": "child_page", "child_page": {"title": "Sub"}}
    ) == "[page] Sub"
    assert notion_fmt.block_to_line(
        {"type": "image", "image": {"type": "external", "external": {"url": "u"}}}
    ) == "[image] u"
    assert notion_fmt.block_to_line(
        {"type": "table_row", "table_row": {"cells": [
            [{"text": {"content": "a"}}], [{"text": {"content": "b"}}]]}}
    ) == "a | b"
    assert notion_fmt.block_to_line({"type": "unknown_type", "unknown_type": {}}) == "[unknown_type]"
    assert notion_fmt.block_to_line({"type": "paragraph"}) is None  # missing body


def test_page_summary():
    s = notion_fmt.page_summary(_page("abc", "T"))
    assert s["id"] == "abc" and s["title"] == "T"
    assert s["url"] == "https://notion.so/abc"


def test_page_to_atom_khan_shape():
    atom = atoms.page_to_atom(_page("p9", "Doc"), "notion://database/d1")
    assert atom["id"] == "p9"
    assert atom["title"] == "Doc"
    assert atom["tags"] == ["notion"]
    assert atom["source"] == "notion://database/d1"
    assert atom["extra"]["parent"] == {"type": "workspace"}
    with pytest.raises(ValueError):
        atoms.page_to_atom({"object": "page"}, "x")


def test_ingest_file(tmp_path):
    f = tmp_path / "export.notion.json"
    f.write_text(json.dumps([_page("a"), _page("b", "Two")]))
    out = list(atoms.ingest(str(f)))
    assert [a["id"] for a in out] == ["a", "b"]


def test_ingest_notion_uri():
    class FakeClient:
        def query_database(self, dbid, **kw):
            assert dbid == "db1"
            return [_page("r1"), _page("r2", "R2")]

    out = list(atoms.ingest("notion://database/db1", FakeClient()))
    assert [a["id"] for a in out] == ["r1", "r2"]


def test_ingest_rejects_bad_uri():
    with pytest.raises(ValueError):
        list(atoms.ingest("https://example.com/x"))
    with pytest.raises(ValueError):
        list(atoms.ingest("notion://other/x", object()))


def test_can_ingest():
    assert atoms.can_ingest("notion://database/x")
    assert atoms.can_ingest("/tmp/foo.notion.json")
    assert not atoms.can_ingest("https://x")
