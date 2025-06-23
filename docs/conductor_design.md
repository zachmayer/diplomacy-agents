# Diplomacy-Agents · Event-Driven "Conductor" Architecture

(seed = 42 · every event ⇒ agent.run · full history · no time-outs)

## 0 · Why this document exists
The original implementation used one `agent.run()` per phase and forced agents to **pull** new information with tools (`view_messages`, `get_board_state`, …).
This redesign introduces a **push-based conductor** that:

1. broadcasts every press, board update, and phase change **as soon as it occurs**,
2. re-invokes the relevant agent **immediately** with the updated history,
3. lets agents chat → submit orders → chat → overwrite orders naturally,
4. keeps all unsafe casts inside `engine.py` (type-safety contract intact).

All code changes are confined to new modules or small, straight edits—PyRight stays green throughout.

## 1 · Top-level decisions
| Topic | Choice | Rationale |
|-------|--------|-----------|
| RNG seed | `42` (constant) | Reproducible runs; no CLI arg needed. |
| Event → run | Every event (including sender's) wakes the agent. | Simpler logic; ensures self-echo context. |
| History passed | Entire accumulated `message_history`. | Easy; avoids token-window bookkeeping. |
| Orders timeout | **None.** Game waits until all 7 have submitted at least once. | Eliminates dead-lock risk from forgotten commit flags. |
| `wait` flag | Always `wait=False`. | Draft/commit distinction not needed; last submission overwrites. |
| History tool | Removed (`view_messages` deleted). | Push model makes it redundant. |
| Extra power list | **None.** Use `game.powers` or `literals.Power`. | Avoid duplication and maintenance errors. |

## 2 · Files & module map
| Path | Status | Purpose |
|------|--------|---------|
| `diplomacy_agents/conductor.py` | NEW | Event bus, `GameManager`, `GameRPC`, `driver()`, `Event` model. |
| `diplomacy_agents/agent.py` | EDIT | Switch deps to `GameRPC`, delete `view_messages`, make two tools async. |
| `diplomacy_agents/cli.py` | EDIT | Add `conductor` command (make run uses it). |
| `tests/test_conductor_smoke.py` | NEW | 0.3 s async smoke test that a phase exists. |
| `Makefile` | EDIT | `run:` target → `uv run -m diplomacy_agents.cli conductor`. |
| `README.md` | EDIT | Update quick-start. |

## 3 · Data structures
```python
from dataclasses import dataclass
from typing import Any, Literal

@dataclass(slots=True, frozen=True)
class Event:
    kind: Literal["PRESS", "BOARD_STATE", "PHASE_CHANGE", "SYSTEM"]
    payload: dict[str, Any]
    sender: str                  # 'SYSTEM' | Power
    recipient: str               # 'ALL' | Power
    ts: float
```

**Queues – one per power:**
```python
self.inboxes: dict[Power, asyncio.Queue[Event]]
```

## 4 · GameManager (conductor)
```python
class GameManager:
    def __init__(self, *, seed: int = 42):
        random.seed(seed)
        self.game = Game(rules={"NO_DEADLINE", "ALWAYS_WAIT", "CD_DUMMIES"})
        self.inboxes = {p: asyncio.Queue() for p in self.game.powers}
        self._orders_buf: dict[Power, list[Order]] = {}
        asyncio.create_task(self._main_loop())
```
**Public RPC called by agents**
```python
async def handle_press(self, sender: Power, to: str, text: str):
    press = PressMessage(to=to, text=text)
    send_press(self.game, sender, press)          # writes to engine
    await self._broadcast("PRESS", press.model_dump(), sender, to)

async def handle_orders(self, pwr: Power, orders: list[Order]) -> bool:
    legal = {o for loc_orders in legal_orders(self.game, pwr).values() for o in loc_orders}
    if not all(o in legal for o in orders):
        return False
    self.game.set_orders(pwr, orders, wait=False)
    self._orders_buf[pwr] = orders
    await self._broadcast("SYSTEM", {"status": "ORDERS_SUBMITTED", "power": pwr}, "SYSTEM", "ALL")
    return True
```
**Broadcast helper**
```python
async def _broadcast(self, kind, payload, sender, recipient):
    ev = Event(kind, payload, sender, recipient, time.time())
    targets = self.inboxes.keys() if recipient == "ALL" else [recipient]
    for t in targets:
        self.inboxes[t].put_nowait(ev)            # includes sender
```
**Phase loop**
```python
async def _main_loop(self):
    await self._broadcast("BOARD_STATE", snapshot_board(self.game).model_dump(), "SYSTEM", "ALL")
    while not self.game.is_game_done:
        while len(self._orders_buf) < len(self.game.powers):
            await asyncio.sleep(0.1)
        self._orders_buf.clear()
        self.game.process()
        await self._broadcast("BOARD_STATE", snapshot_board(self.game).model_dump(), "SYSTEM", "ALL")
        await self._broadcast("PHASE_CHANGE", {"phase": self.game.get_current_phase()}, "SYSTEM", "ALL")
```

## 5 · GameRPC (deps)
```python
from dataclasses import dataclass

@dataclass(slots=True, frozen=True)
class GameRPC:
    power: Power
    gm: GameManager

    def board_state(self) -> BoardState:
        return snapshot_board(self.gm.game)

    def my_possible_orders(self) -> dict[Location, list[Order]]:
        return legal_orders(self.gm.game, self.power)

    async def send_press(self, to: str, text: str):
        await self.gm.handle_press(self.power, to, text)

    async def submit_orders(self, orders: list[Order]) -> bool:
        return await self.gm.handle_orders(self.power, orders)
```

## 6 · Driver coroutine
```python
async def driver(power, agent, inbox, rpc):
    history: list[ModelMessage] = []
    while True:
        ev = await inbox.get()
        history.append(_to_chat(ev, power))       # convert Event → ModelMessage
        await agent.run("NEW_EVENT", deps=rpc, message_history=history)
```
**`_to_chat()` mapping**
| kind | role | content |
|------|------|---------|
| PRESS | "user" if recipient == power else "assistant" | "{sender}→{recipient}: {text}" |
| BOARD_STATE | "system" | `"BOARD_STATE {phase}: {json}"` |
| PHASE_CHANGE | "system" | `"PHASE_CHANGE: {phase}"` |
| SYSTEM | "system" | `json.dumps(payload)` |

## 7 · Edits to `agent.py`
*Deps* = `GameRPC`.

* Delete `view_messages` tool.
* Tools now call RPC:
```python
def get_board_state(ctx):
    return ctx.deps.board_state()

def get_my_possible_orders(ctx):
    return MyPossibleOrders(orders=ctx.deps.my_possible_orders())
```
* `send_message` / `submit_orders` become **async** and `await` RPC methods.

## 8 · CLI integration
```python
@cli.command("conductor", help="Run self-play with event-driven conductor.")
def conductor_cmd() -> None:
    asyncio.run(_run_conductor())

async def _run_conductor():
    gm = GameManager(seed=42)
    tasks = []
    for p in gm.game.powers:
        rpc = GameRPC(power=p, gm=gm)
        agent = build_agent(rpc, model_name=DEFAULT_MODEL)
        tasks.append(asyncio.create_task(driver(p, agent, gm.inboxes[p], rpc)))
    await asyncio.gather(*tasks)
```
**Makefile target:**
```makefile
run:  ## Run event-driven self-play match (seed 42)
	uv run -m diplomacy_agents.cli conductor
```

## 9 · Testing
`tests/test_conductor_smoke.py`
```python
import asyncio
from diplomacy_agents.conductor import GameManager, GameRPC, driver
from diplomacy_agents.agent import build_agent, DEFAULT_MODEL

async def _smoke():
    gm = GameManager()
    pwr = gm.game.powers[0]
    rpc = GameRPC(power=pwr, gm=gm)
    agent = build_agent(rpc, model_name=DEFAULT_MODEL)
    asyncio.create_task(driver(pwr, agent, gm.inboxes[pwr], rpc))
    await asyncio.sleep(0.3)
    assert gm.game.get_current_phase()

def test_smoke():
    asyncio.run(_smoke())
```

## 10 · Roll-out steps
1. Branch: `git checkout -b feat/conductor`.
2. Add `conductor.py`, edit the files above.
3. `make check-all` – fix any type errors.
4. `make run` – ensure game completes; observe console.
5. Delete legacy self-play command if desired.
6. Merge & tag `v0.2.0`.

## 11 · Future extensions (non-blocking)
* **WebSocket spectator UI** – subscribe to each inbox for real-time board display.
* **Deadline timer** – add optional timeout in `GameManager._main_loop`.
* **History windowing** – truncate history to last N tokens if context becomes too large.

---
*Drop this file into `docs/conductor_design.md`; the table of contents in your README can link to it for reference.* 