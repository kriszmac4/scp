#!/usr/bin/env python3
"""
SCP — Session Context Pre-fill for Hermes Agent
══════════════════════════════════════════════════

Automatically generates a session_context.md file that gets injected into
every Hermes session via the `prefill_messages_file` config option.

Data sources:
  - ICM (Infinite Context Memory): active topics, recent entries, high-importance items
  - Holographic (fact_store / memory_store.db): trusted facts
  - Marveen Dream Engine: latest nightly consolidation report
  - Marveen Bus: pending inter-agent messages

Usage:
  python3 scp.py --profile dev
  python3 scp.py --profile research --output /tmp/scp_context.md
  python3 scp.py --hermes-home /custom/path/.hermes --profile general

Environment variables:
  HERMES_HOME   — path to Hermes root (default: ~/.hermes)
  HERMES_PROFILE — profile name (default: dev)

Watchdog mode (for no_agent cron):
  Script exits with 0 and silent stdout on success.
  On error, prints to stderr and exits non-zero.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


# ─── Defaults ────────────────────────────────────────────────

DEFAULT_HERMES_HOME = os.path.join(str(Path.home()), ".hermes")
DEFAULT_PROFILE = "dev"
SCP_VERSION = "1.0.0"


# ─── Path resolution ─────────────────────────────────────────

def resolve_paths(hermes_home: str, profile: str) -> dict:
    """Resolve all data source paths for a given Hermes home + profile."""
    home = Path(hermes_home).expanduser().resolve()
    profile_home = home / "profiles" / profile / "home"

    return {
        "icm_db": str(profile_home / ".local/share/icm/memories.db"),
        "memory_store": str(home / "profiles" / profile / "memory_store.db"),
        "amb_data": str(home / "profiles" / profile / "data/agent_message_bus"),
        "output_dir": str(home / "profiles" / profile / "data"),
        "output_file": str(home / "profiles" / profile / "data/session_context.md"),
        "hermes_home": str(home),
        "profile": profile,
    }


# ─── ICM Context ─────────────────────────────────────────────

def get_icm_context(icm_db: str) -> str:
    """
    Query ICM database for:
      1. Active topics (count + avg weight)
      2. Recent memory entries
      3. High-importance entries (critical/high)
    """
    if not os.path.exists(icm_db):
        return ""

    conn = sqlite3.connect(icm_db)
    conn.row_factory = sqlite3.Row
    parts = []

    try:
        # 1. Active topics
        topics = conn.execute("""
            SELECT topic, COUNT(*) as cnt, ROUND(AVG(weight), 2) as avg_w
            FROM memories
            WHERE topic IS NOT NULL
            GROUP BY topic
            ORDER BY cnt DESC, avg_w DESC
            LIMIT 10
        """).fetchall()

        if topics:
            parts.append("📚 **ICM — Active Topics:**")
            for t in topics:
                parts.append(f"  • {t['topic']}: {t['cnt']} entries (avg weight: {t['avg_w']})")
            parts.append("")

        # 2. Recent entries
        recent = conn.execute("""
            SELECT topic, summary, created_at, importance
            FROM memories
            WHERE summary IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 5
        """).fetchall()

        if recent:
            parts.append("🆕 **ICM — Recent Entries:**")
            for r in recent:
                summary = r['summary'][:120] + "…" if len(r['summary']) > 120 else r['summary']
                imp = f" [{r['importance']}]" if r['importance'] else ""
                parts.append(f"  • {summary} (topic: {r['topic']}{imp})")
            parts.append("")

        # 3. High-importance entries
        high = conn.execute("""
            SELECT topic, summary, weight, created_at
            FROM memories
            WHERE importance IN ('critical', 'high')
            ORDER BY weight DESC
            LIMIT 5
        """).fetchall()

        if high:
            parts.append("⭐ **ICM — Critical / High Importance:**")
            for h in high:
                summary = h['summary'][:120] + "…" if len(h['summary']) > 120 else h['summary']
                parts.append(f"  • [{h['topic']}] {summary} (w={h['weight']})")
            parts.append("")

    finally:
        conn.close()

    return "\n".join(parts)


# ─── Holographic Context ─────────────────────────────────────

def get_holographic_context(memory_store: str) -> str:
    """
    Query Holographic Memory Store for trusted facts.
    Orders by helpful-to-retrieval ratio so the most useful facts surface first.
    """
    if not os.path.exists(memory_store):
        return ""

    conn = sqlite3.connect(memory_store)
    conn.row_factory = sqlite3.Row
    parts = []

    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "facts" not in tables:
            return ""

        facts = conn.execute("""
            SELECT content, category, tags, trust_score,
                   retrieval_count, helpful_count, created_at
            FROM facts
            WHERE trust_score >= 0.3
            ORDER BY
                (helpful_count * 1.0 / CASE WHEN retrieval_count = 0 THEN 1 ELSE retrieval_count END) DESC,
                retrieval_count DESC,
                trust_score DESC
            LIMIT 6
        """).fetchall()

        if facts:
            parts.append("🧠 **Holographic Memory — Key Facts:**")
            for f in facts:
                content = f['content'][:150] + "…" if len(f['content']) > 150 else f['content']
                score = f"{f['trust_score']:.1f}"
                helpful = f" ({f['helpful_count']}/{f['retrieval_count']} helpful)" if f['retrieval_count'] > 0 else ""
                parts.append(f"  • [{f['category']}] {content} (trust: {score}{helpful})")
            parts.append("")

    finally:
        conn.close()

    return "\n".join(parts)


# ─── Marveen Context ────────────────────────────────────────

def get_amb_context(amb_data: str) -> str:
    """
    Query Marveen subsystem:
      1. Latest Dream Engine consolidation report
      2. Pending inter-agent message count
    """
    parts = []

    # 1. Dream engine report
    dreams_dir = os.path.join(amb_data, "dreams")
    if os.path.exists(dreams_dir):
        dreams = sorted(
            [f for f in os.listdir(dreams_dir) if f.endswith(".md")],
            reverse=True,
        )
        if dreams:
            latest = dreams[0]
            path = os.path.join(dreams_dir, latest)
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                preview = content[:500] + "…" if len(content) > 500 else content
                parts.append(f"🌙 **Marveen Dream Engine — Last Report ({latest}):**")
                parts.append(preview)
                parts.append("")
            except Exception:
                pass

    # 2. Pending messages
    msg_db = os.path.join(amb_data, "agent_messages.db")
    if os.path.exists(msg_db):
        try:
            conn = sqlite3.connect(msg_db)
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE status IN ('pending', 'delivered')"
            ).fetchone()[0]
            conn.close()
            if count > 0:
                parts.append(f"📨 **Marveen Bus — Pending Messages:** {count}")
                parts.append("")
        except Exception:
            pass

    return "\n".join(parts)


# ─── CLI ─────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="SCP — Session Context Pre-fill for Hermes Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scp.py --profile dev
  python3 scp.py --profile research --output /tmp/ctx.md
  python3 scp.py --hermes-home /custom/path/.hermes --profile general

  # Run as no_agent cron (silent on success):
  python3 scp.py --profile dev --watchdog
        """,
    )

    parser.add_argument(
        "--profile", "-p",
        default=os.environ.get("HERMES_PROFILE", DEFAULT_PROFILE),
        help=f"Hermes profile name (default: {DEFAULT_PROFILE}, or $HERMES_PROFILE)",
    )

    parser.add_argument(
        "--hermes-home", "-H",
        default=os.environ.get("HERMES_HOME", DEFAULT_HERMES_HOME),
        help=f"Hermes root path (default: {DEFAULT_HERMES_HOME}, or $HERMES_HOME)",
    )

    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output file path (default: auto-detected from profile)",
    )

    parser.add_argument(
        "--watchdog", "-w",
        action="store_true",
        default=False,
        help="Watchdog mode: silent on success, non-zero exit on error",
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"SCP {SCP_VERSION}",
    )

    return parser.parse_args(argv)


# ─── Main ────────────────────────────────────────────────────

def main():
    args = parse_args()
    paths = resolve_paths(args.hermes_home, args.profile)

    output_file = args.output or paths["output_file"]

    # Collect sections
    sections = [
        f"# 📋 Session Context — SCP v{SCP_VERSION}",
        f"_Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}_",
        f"_Hermes: {paths['hermes_home']} | Profile: {paths['profile']}_",
        "",
    ]

    icm = get_icm_context(paths["icm_db"])
    if icm:
        sections.append(icm)

    holo = get_holographic_context(paths["memory_store"])
    if holo:
        sections.append(holo)

    mar = get_amb_context(paths["amb_data"])
    if mar:
        sections.append(mar)

    # Footer
    sections.append("---")
    sections.append("_Generated by SCP (Session Context Pre-fill) — refreshed by cron._")
    sections.append("_Sources: ICM | Holographic Memory | Marveen Dream Engine | Marveen Bus_")

    output = "\n".join(sections)

    # Write output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output)
    except OSError as e:
        if args.watchdog:
            print(f"SCP ERROR: Cannot write {output_file}: {e}", file=sys.stderr)
            sys.exit(1)
        raise

    # Watchdog mode: silent on success
    if not args.watchdog:
        print(f"[SCP] Context written to {output_file} ({len(output)} chars)")


if __name__ == "__main__":
    main()
