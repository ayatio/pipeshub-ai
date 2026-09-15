"""Offline tests for heading-aware chunking. No DB, no network."""
from living_brain.chunking import chunk_markdown


def test_empty_input_yields_no_chunks():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n  ") == []


def test_headings_build_breadcrumb_path():
    md = "# Meeting\n\nintro\n\n## Decisions\n\nWe chose Postgres.\n"
    chunks = chunk_markdown(md)
    paths = [c.heading_path for c in chunks]
    assert "Meeting" in paths
    assert "Meeting > Decisions" in paths


def test_title_seeds_path_and_prefixes_content():
    chunks = chunk_markdown("plain body text", title="my-note")
    assert len(chunks) == 1
    assert chunks[0].heading_path == "my-note"
    # breadcrumb is prefixed into the embeddable content
    assert chunks[0].content.startswith("my-note")
    assert "plain body text" in chunks[0].content


def test_sibling_headings_pop_stack():
    md = "## A\n\naaa\n\n## B\n\nbbb\n"
    paths = [c.heading_path for c in chunk_markdown(md)]
    assert paths == ["A", "B"]


def test_deeper_then_shallower_heading():
    md = "# A\n\na\n\n## B\n\nb\n\n# C\n\nc\n"
    paths = [c.heading_path for c in chunk_markdown(md)]
    assert paths == ["A", "A > B", "C"]


def test_large_section_packs_by_paragraph():
    paras = "\n\n".join(f"para {i} " + "x" * 300 for i in range(6))
    md = f"# Big\n\n{paras}\n"
    chunks = chunk_markdown(md, max_chars=700)
    assert len(chunks) > 1
    assert all(c.heading_path == "Big" for c in chunks)


def test_deterministic():
    md = "# H\n\nsome text\n\n## Sub\n\nmore text\n"
    assert [c.content for c in chunk_markdown(md)] == [
        c.content for c in chunk_markdown(md)
    ]
