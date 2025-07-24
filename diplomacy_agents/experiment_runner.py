"""
Batch self-play experiment runner.

Runs a single game with configurable press rounds and optional year cap,
persists artefacts, and appends a summary row to ``results.csv``.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import logging
import random
import random as _rnd
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

import pandas as pd

# Pricing util
from tokonomics import calculate_token_cost

from diplomacy_agents.enums import Power
from diplomacy_agents.orchestrator import GameOrchestrator, PowerModelMap

# Press export removed – gunboat mode has no messaging.

logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESULTS_CSV = Path("results.csv")

# https://ai.pydantic.dev/api/models/base/
MODEL_UNIVERSE: tuple[str, ...] = (
    # OpenAI
    # "openai:gpt-4.1-2025-04-14",
    # "openai:gpt-4.1-mini-2025-04-14",
    "openai:gpt-4.1-nano-2025-04-14",
    # "openai:gpt-4o-2024-11-20",
    # "openai:gpt-4o-mini-2024-07-18",
    # "openai:o3-2025-04-16",
    # "openai:o3-mini-2025-01-31",
    # "openai:o4-mini-2025-04-16",
    # Google
    "google-gla:gemini-2.5-flash",
    # "google-gla:gemini-2.5-pro",
    # Anthropic
    # "anthropic:claude-4-opus-20250514",
    # "anthropic:claude-4-sonnet-20250514",
    # DeepSeek
    # "deepseek:deepseek-reasoner",
    # Baselines
    "hold",
    "random",
)

__all__ = ["ExperimentRunner"]


class ExperimentRunner:
    """Batch self-play experiment runner."""

    def __init__(self, *, messaging_rounds: int = 3, seed: int = 42, max_year: int | None = 1951) -> None:
        """
        Store common configuration for a batch of experiments.

        Parameters
        ----------
        messaging_rounds
            Number of press rounds per movement phase.
        seed
            Seed for the global ``random`` module to obtain reproducible model
            assignments across runs.  Defaults to ``42`` to preserve existing
            behaviour when the parameter is omitted.
        max_year
            Optional hard cap on the simulation year.  When provided, games
            terminate once the board reaches *or passes* this year (e.g.
            ``1905`` for short smoke tests).  ``None`` disables the cap and
            lets the upstream diplomacy engine run until its own internal
            limit of 2000.

        """
        self.messaging_rounds = messaging_rounds
        self.seed = seed
        self.max_year = max_year

        # Ensure deterministic randomness for this runner instance.
        _rnd.seed(seed)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _random_model_map() -> PowerModelMap:
        """Return a freshly-minted mapping {power: model_name}."""
        return cast(PowerModelMap, {p: random.choice(MODEL_UNIVERSE) for p in Power})

    @staticmethod
    def _experiment_hash(
        model_map: PowerModelMap,
        messaging_rounds: int,
        max_year: int | None,
    ) -> str:
        """Return 8-char SHA-1 hash for *model_map*, *messaging_rounds* and *max_year*."""
        mapping_repr = json.dumps(dict(model_map), sort_keys=True)
        # ``max_year`` may be ``None`` – include as literal string so differing
        # caps produce distinct hashes.
        hash_input = f"{messaging_rounds}:{max_year}:{mapping_repr}"
        return hashlib.sha1(hash_input.encode()).hexdigest()[:8]

    # ------------------------------------------------------------------
    # Core async workflow
    # ------------------------------------------------------------------

    async def _run_once_async(self, model_map: PowerModelMap | None) -> dict[str, Any]:
        """
        Run one game, persist artefacts, append CSV row, return metrics.

        If *model_map* is ``None``, a random assignment is generated as before;
        otherwise, the supplied mapping is used verbatim.  This makes smoke
        tests deterministic and enables bespoke experiments without modifying
        internal code.
        """
        # Generate parameters ------------------------------------------------
        if model_map is None:
            model_map = self._random_model_map()
        exp_hash = self._experiment_hash(model_map, self.messaging_rounds, self.max_year)

        # --------------------------------------------------------------
        # Short-circuit when results already exist
        # --------------------------------------------------------------
        if RESULTS_CSV.exists():
            with RESULTS_CSV.open(newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("hash") == exp_hash:
                        logger.info("Found previous run – returning its row as a plain dict.")
                        return row

        # No global state to clear – per-agent token totals are reset with new agent instances.

        orch = GameOrchestrator(
            model_map=model_map,
            messaging_rounds=self.messaging_rounds,
            max_year=self.max_year,
        )
        final_centers = await orch.run()

        # --------------------------------------------------------------
        # Metrics aggregation
        # --------------------------------------------------------------
        runtime_by_power: dict[str, float] = {p: a.total_runtime_s for p, a in orch.agents.items()}

        # Aggregate tokens per power
        token_by_power: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"prompt": 0, "response": 0})
        for power, agent in orch.agents.items():
            for _model, buckets in agent.token_totals.items():
                token_by_power[power]["prompt"] += buckets.get("request_tokens", buckets.get("prompt", 0))
                token_by_power[power]["response"] += buckets.get("response_tokens", buckets.get("response", 0))

        # Compute cost per power
        cost_by_power: dict[str, float] = {}
        for power, agent in orch.agents.items():
            total_cost = 0.0
            for model_id, buckets in agent.token_totals.items():
                prompt = buckets.get("request_tokens", buckets.get("prompt", 0))
                completion = buckets.get("response_tokens", buckets.get("response", 0))

                if not (prompt or completion):
                    continue

                token_costs = await calculate_token_cost(
                    model=model_id,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                )
                if token_costs is not None:
                    total_cost += float(token_costs.total_cost)
            cost_by_power[power] = total_cost

        # Emit human-readable summary ---------------------------------------------------
        total_usd = sum(cost_by_power.values())
        logger.info("Total LLM cost this run: $%.4f", total_usd)

        # --------------------------------------------------------------
        # Artefact persistence
        # --------------------------------------------------------------
        arte_dir = Path("artifacts") / exp_hash
        arte_dir.mkdir(parents=True, exist_ok=True)

        # DATC game state
        orch.engine.save(str(arte_dir / f"game_{exp_hash}.datc"))

        # SVG animation
        orch.save_animation(arte_dir / f"animation_{exp_hash}.svg")

        # Press markdown removed – no press in gunboat mode.

        # --------------------------------------------------------------
        # CSV append (one row)
        # --------------------------------------------------------------
        row: dict[str, Any] = {"hash": exp_hash}

        # Centres ------------------------------------------------------
        for p in Power:
            row[f"centres_{p}"] = final_centers.get(p, 0)

        # Tokens -------------------------------------------------------
        for p in Power:
            toks = token_by_power.get(p, {"prompt": 0, "response": 0})
            row[f"prompt_{p}"] = toks["prompt"]
            row[f"response_{p}"] = toks["response"]

        # Runtime ------------------------------------------------------
        for p in Power:
            row[f"runtime_{p}"] = runtime_by_power.get(p, 0.0)

        # Cost ---------------------------------------------------------
        for p in Power:
            row[f"cost_{p}"] = cost_by_power.get(p, 0.0)

        # Model names --------------------------------------------------
        for p in Power:
            row[f"model_{p}"] = model_map[p]

        df_row = pd.DataFrame([row])
        if RESULTS_CSV.exists():
            df_row.to_csv(RESULTS_CSV, mode="a", index=False, header=False)
        else:
            df_row.to_csv(RESULTS_CSV, mode="w", index=False)

        # Return collected data for interactive callers ----------------
        return row

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self, *, model_map: PowerModelMap | None = None) -> dict[str, Any]:
        """
        Blocking wrapper around the async workflow.

        Parameters
        ----------
        model_map
            Explicit power→model mapping.  When omitted, a random mapping is
            generated using the runner's seed-controlled RNG.

        """
        return asyncio.run(self._run_once_async(model_map))
