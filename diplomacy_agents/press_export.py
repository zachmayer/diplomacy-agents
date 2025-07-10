"""
Utilities for exporting press messages to Markdown files.

This module centralises the formatting logic so that it can be reused by both
single-game orchestrations and large batch experiment runs.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def save_press_markdown(
    entries: Iterable[tuple[str, int, str, str, str]],
    model_map: Mapping[str, object],
    game_hash: str,
    output_path: Path,
) -> None:
    """
    Write *entries* to *output_path* grouped by phase & round.

    Parameters
    ----------
    entries
        An iterable of ``(phase, round, sender, recipient, text)`` tuples.
    model_map
        Mapping from power (ENGLAND, FRANCE, …) to model name used.
    game_hash
        Short SHA-1 hash identifying the match (used in heading).
    output_path
        Target Markdown path – directories are created automatically.

    """
    grouped: dict[str, list[tuple[int, str, str, str]]] = defaultdict(list)
    for phase, rnd, sender, recipient, text in entries:
        grouped[phase].append((rnd, sender, recipient, text))

    lines: list[str] = [f"# Press History ({game_hash})\n", "## Power Assignments"]
    for p in sorted(model_map):
        lines.append(f"- {p}: {model_map[p]}")
    lines.append("")
    lines.append("")
    for phase in sorted(grouped):
        lines.append(f"## {phase}")
        # Group by round within the phase.
        rounds = sorted({entry[0] for entry in grouped[phase]})
        for rnd in rounds:
            lines.append(f"\n### Round {rnd}\n")
            for entry in grouped[phase]:
                if entry[0] == rnd:
                    _, sender, recipient, text = entry
                    lines.append(f"- {sender} → {recipient}: {text}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
