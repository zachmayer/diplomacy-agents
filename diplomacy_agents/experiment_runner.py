"""
Batch self-play experiment runner.

Runs a single game with configurable year cap and persists artifacts.
Appends a summary row to ``results.csv``.
"""

from __future__ import annotations

import hashlib
import logging
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from tokonomics import calculate_token_cost

from diplomacy_agents.enums import Power
from diplomacy_agents.orchestrator import AgentSpecName, GameOrchestrator, PowerModelMap

logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESULTS_CSV = Path("results.csv")

# https://ai.pydantic.dev/api/models/base/
MODEL_UNIVERSE: tuple[AgentSpecName, ...] = (
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

    # TODO: WHEN DONE TESTING, CHANGE MAX_YEAR TO 1951
    def __init__(self, *, model_map: PowerModelMap | None = None, seed: int = 42, max_year: int | None = 1905) -> None:
        """Run a single experiment against the orchestrator."""
        random.seed(seed)
        self.seed = seed
        self.max_year = max_year
        if model_map is None:
            model_map = PowerModelMap(
                AUSTRIA=random.choice(MODEL_UNIVERSE),
                ENGLAND=random.choice(MODEL_UNIVERSE),
                FRANCE=random.choice(MODEL_UNIVERSE),
                GERMANY=random.choice(MODEL_UNIVERSE),
                ITALY=random.choice(MODEL_UNIVERSE),
                RUSSIA=random.choice(MODEL_UNIVERSE),
                TURKEY=random.choice(MODEL_UNIVERSE),
            )
        self.model_map = model_map
        run_id = f"{self.max_year}:{self.model_map.model_dump()}"
        run_id = hashlib.sha1(run_id.encode()).hexdigest()[:8]
        self.run_id = run_id
        self.orch = GameOrchestrator(
            model_map=self.model_map,
            max_year=self.max_year,
        )

    # ------------------------------------------------------------------
    # Core async workflow
    # ------------------------------------------------------------------

    async def run_once(self) -> dict[str, Any]:
        """
        Run one game, persist artifacts, append CSV row, return metrics.

        If *model_map* is ``None``, a random assignment is generated.
        Otherwise, the supplied mapping is used verbatim.
        """
        final_centers = await self.orch.run()

        # --------------------------------------------------------------
        # Metrics aggregation
        # --------------------------------------------------------------
        runtime_by_power: dict[str, float] = {p: a.total_runtime_s for p, a in self.orch.agents.items()}

        # Aggregate tokens per power
        token_by_power: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"prompt": 0, "response": 0})
        for power, agent in self.orch.agents.items():
            for _model, buckets in agent.token_totals.items():
                token_by_power[power]["prompt"] += buckets.get("request_tokens", buckets.get("prompt", 0))
                token_by_power[power]["response"] += buckets.get("response_tokens", buckets.get("response", 0))

        # Compute cost per power
        cost_by_power: dict[str, float] = {}
        for power, agent in self.orch.agents.items():
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
        # Artifact persistence
        # --------------------------------------------------------------
        run_dir = Path("artifacts") / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # DATC game state
        self.orch.engine.save(str(run_dir / f"game_{self.run_id}.datc"))

        # SVG animation
        self.orch.save_animation(run_dir / f"animation_{self.run_id}.svg")

        # --------------------------------------------------------------
        # CSV append (one row)
        # --------------------------------------------------------------
        row: dict[str, Any] = {}

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
            row[f"model_{p}"] = getattr(self.model_map, p.name)

        df_row = pd.DataFrame([row])
        if RESULTS_CSV.exists():
            df_row.to_csv(RESULTS_CSV, mode="a", index=False, header=False)
        else:
            df_row.to_csv(RESULTS_CSV, mode="w", index=False)

        # Return collected data for interactive callers ----------------
        return row
