import asyncio
from dataclasses import dataclass
from typing import Literal

from diplomacy import Game
from pydantic import BaseModel, Field, create_model

# Base types
PowerName = Literal["AUSTRIA", "ENGLAND", "FRANCE", "GERMANY", "ITALY", "RUSSIA", "TURKEY"]
Location = str
UnitType = Literal["A", "F"]
OrderDict = dict[Location, str] 

# --- Simple DTOs ---


@dataclass(frozen=True)
class GameStateDTO:
    """What the orchestrator needs."""

    phase: str
    year: int
    is_game_done: bool
    powers: tuple[PowerName, ...]
    supply_centers: dict[PowerName, int]


@dataclass(frozen=True)
class PowerViewDTO:
    """What one power sees for ordering."""

    power: PowerName
    phase: str
    units: dict[Location, UnitType]
    valid_orders: dict[Location, tuple[str, ...]]

    def create_order_model(self) -> type[BaseModel]:
        """Generate Pydantic model with Literal constraints."""
        fields = {
            location: (Literal[orders], Field(description=f"Order for {location}"))
            for location, orders in self.valid_orders.items()
        }
        return create_model(f"Orders_{self.power}_{self.phase}", **fields)


# --- Engine Wrapper ---


class DiplomacyEngine:
    """Minimal wrapper providing DTOs."""

    def __init__(self) -> None:
        self._game = Game()

    def get_game_state(self) -> GameStateDTO:
        return GameStateDTO(
            phase=self._game.get_current_phase(),
            year=int(self._game.get_current_phase()[1:5]),
            is_game_done=self._game.is_game_done,
            powers=tuple(self._game.powers),
            supply_centers={p: len(self._game.get_centers(p)) for p in self._game.powers},
        )

    def get_power_view(self, power: PowerName) -> PowerViewDTO:
        all_possible = self._game.get_all_possible_orders()
        orderable = self._game.get_orderable_locations(power)

        valid_orders = {loc: tuple(all_possible[loc]) for loc in orderable if loc in all_possible}

        return PowerViewDTO(
            power=power,
            phase=self._game.get_current_phase(),
            units=self._parse_units(self._game.get_units(power)),
            valid_orders=valid_orders,
        )

    def submit_orders(self, power: PowerName, orders: dict[Location, str]) -> None:
        order_list = list(orders.values())
        self._game.set_orders(power, order_list)

    def process_turn(self) -> None:
        self._game.process()

    def _parse_units(self, unit_strings: list[str]) -> dict[Location, UnitType]:
        result = {}
        for unit in unit_strings:
            unit_type, location = unit.split(" ", 1)
            result[location] = unit_type
        return result


# --- Simple Agent ---

from pydantic_ai import Agent


class OrderAgent:
    """Agent that only submits orders."""

    def __init__(self, power: PowerName, model: str) -> None:
        self.power = power
        self.model = model

    async def get_orders(self, view: PowerViewDTO) -> dict[Location, str]:
        """Get orders using dynamic model from DTO."""
        # Create model for this exact game state
        OrderModel = view.create_order_model()

        # One-shot agent with dynamic model
        agent = Agent(
            self.model, result_type=OrderModel, retries=3, system_prompt="Select one order per unit from the schema."
        )

        # Simple prompt
        prompt = f"""You are {view.power} in Diplomacy.

Phase: {view.phase}
Your units: {list(view.units.keys())}

Select one order for each unit. The schema shows all valid options."""

        try:
            result = await agent.run(prompt)

            # Extract orders from dynamic model
            return {location: getattr(result.data, location) for location in view.valid_orders}

        except Exception:
            # Return hold orders
            return {loc: f"{view.units[loc]} {loc} H" for loc in view.units}


# --- Simple Orchestrator ---


class SimpleOrchestrator:
    """Minimal game runner."""

    def __init__(self) -> None:
        self.engine = DiplomacyEngine()
        self.agents = self._create_agents()

    def _create_agents(self) -> dict[PowerName, OrderAgent]:
        """Create agents with random models."""
        models = [
            "gpt-4o",
            "gpt-4o-mini",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro",
            "gpt-4o",  # Need 7 total
        ]

        game_state = self.engine.get_game_state()
        return {power: OrderAgent(power, model) for power, model in zip(game_state.powers, models, strict=False)}

    async def run_game(self) -> dict:
        """Run game - just orders each turn."""
        turns = 0

        while True:
            game_state = self.engine.get_game_state()

            if game_state.is_game_done:
                break

            await self._execute_turn()
            turns += 1

            # Safety limit
            if turns > 100:
                break

        final_state = self.engine.get_game_state()
        return {
            "winner": self._find_winner(final_state),
            "final_centers": final_state.supply_centers,
            "turns_played": turns,
        }

    async def _execute_turn(self) -> None:
        """Execute one turn - just collect orders and process."""
        # Collect orders from all powers in parallel
        tasks = {}

        for power, agent in self.agents.items():
            view = self.engine.get_power_view(power)
            if view.units:  # Only if they have units
                tasks[power] = asyncio.create_task(agent.get_orders(view))

        # Wait for all orders
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # Submit orders
        for power, result in zip(tasks.keys(), results, strict=False):
            if isinstance(result, dict):
                self.engine.submit_orders(power, result)
            else:
                pass

        # Process turn
        self.engine.process_turn()

    def _find_winner(self, state: GameStateDTO) -> PowerName | None:
        """Check for winner (18+ centers)."""
        for power, centers in state.supply_centers.items():
            if centers >= 18:
                return power
        return None


# --- Run it ---


async def main() -> None:
    """Entry point."""
    orchestrator = SimpleOrchestrator()
    result = await orchestrator.run_game()

    for _power, _centers in sorted(result["final_centers"].items(), key=lambda x: x[1], reverse=True):
        pass


if __name__ == "__main__":
    asyncio.run(main())
