"""Command-line interface: brain <command>.

  brain init                 create tables (same as `make migrate`)
  brain ingest [PATH]        ingest a file/dir (default: NOTES_DIR)
  brain night [--duration]   run a consolidation pass
  brain search "query"       semantic search
  brain stats                show counts + backends
  brain insights             list consolidated themes
"""
from __future__ import annotations

from pathlib import Path

import click

from . import migrate, store
from .config import get_settings
from .embeddings import backend_name as embed_backend
from .ingest import ingest_dir, ingest_file, ingest_text
from .llm import backend_name as llm_backend
from .night import run_night
from .search import search as semantic_search
from . import db


@click.group()
def main() -> None:
    """living-brain command line."""


@main.command()
def init() -> None:
    """Create/upgrade the database schema."""
    migrate.main()


@main.command()
@click.argument("path", required=False)
@click.option("--embed/--no-embed", "embed_now", default=False,
              help="embed immediately instead of waiting for the next night run")
@click.option("--text", "text", default=None, help="ingest raw text instead of a path")
def ingest(path: str | None, embed_now: bool, text: str | None) -> None:
    """Ingest notes from a file or directory (defaults to NOTES_DIR)."""
    if text is not None:
        ids = ingest_text(text, source="cli", embed_now=embed_now)
        click.echo(f"ingested {len(ids)} memories from --text")
        return
    target = Path(path or get_settings().notes_dir)
    if not target.exists():
        raise click.ClickException(f"path not found: {target}")
    if target.is_dir():
        res = ingest_dir(target, embed_now=embed_now)
        total = sum(res.values())
        click.echo(f"ingested {total} memories from {len(res)} files in {target}")
    else:
        ids = ingest_file(target, embed_now=embed_now)
        click.echo(f"ingested {len(ids)} memories from {target}")


@main.command()
@click.option("--duration", type=float, default=60, help="time budget in seconds")
@click.option("--quiet", is_flag=True)
def night(duration: float, quiet: bool) -> None:
    """Run a nightly consolidation pass."""
    run_night(duration, verbose=not quiet)


@main.command()
@click.argument("query")
@click.option("-k", "--top-k", type=int, default=5)
def search(query: str, top_k: int) -> None:
    """Semantic search over memories."""
    hits = semantic_search(query, top_k=top_k)
    if not hits:
        click.echo("(no memories yet — ingest some notes and run `brain night`)")
        return
    click.echo(f"embeddings={embed_backend()}\n")
    for i, hit in enumerate(hits, 1):
        m = hit.memory
        title = m.title or (m.source or "memory")
        snippet = " ".join(m.content.split())[:160]
        click.echo(f"{i}. [{hit.score:.3f}] {title}  (#{m.id})")
        click.echo(f"     {snippet}")


@main.command()
def insights() -> None:
    """List consolidated themes the brain has formed."""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT id, title, content, source_ids FROM insights ORDER BY id DESC"
        ).fetchall()
    if not rows:
        click.echo("(no insights yet — run `brain night` after ingesting)")
        return
    for r in rows:
        click.echo(f"#{r['id']}  {r['title']}")
        click.echo(f"     {' '.join(str(r['content']).split())[:220]}")


@main.command()
def stats() -> None:
    """Show counts and active backends."""
    c = store.counts()
    click.echo(f"db          : {db.dialect()}  ({get_settings().database_url})")
    click.echo(f"embeddings  : {embed_backend()}")
    click.echo(f"llm         : {llm_backend()}")
    click.echo(f"memories    : {c['memories']} ({c['embedded']} embedded)")
    click.echo(f"links       : {c['links']}")
    click.echo(f"insights    : {c['insights']}")
    click.echo(f"night runs  : {c['night_runs']}")


if __name__ == "__main__":
    main()
