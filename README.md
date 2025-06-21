# diplomacy-agents

Pydantic AI Agents playing Diplomacy

## Dev quick-start

```bash
brew install git uv
git clone git@github.com:zachmayer/diplomacy-agents.git
cd diplomacy-agents
make install
make types
```

### CI

GitHub Actions runs `make check-ci` for every push & PR.

### Tooling

All config (ruff, pyright) lives in `pyproject.toml`. Makefile is self-documenting:

```bash
make help
```

## Diplomacy

Uses [diplomacy](https://github.com/diplomacy/diplomacy) python package for the game engine. The API docs are very useful:

- https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.game.html
- https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.map.html
- https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.message.html
- https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.power.html
- https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.renderer.html
- https://diplomacy.readthedocs.io/en/stable/api/diplomacy.utils.export.html

## 🛡️ Type-Safety Contract

1. **No `cast()` or `# type: ignore`** outside `diplomacy_agents/engine.py`.  
   • If another file needs a cast, create a typed helper in `engine.py` instead.  
   • The only allowed suppressions are for untyped third-party libraries.

2. **No raw `str` in public APIs.**  
   • Plain strings are for human-readable text.  
   • For tokens, use explicit type aliases from `diplomacy_agents/types.py` (e.g., `Phase`) or `Literal` types from `diplomacy_agents/literals.py` (e.g., `Power`).

3. **Runtime-validated I/O.**  
   • All data structures are defined as Pydantic models in `diplomacy_agents/models.py` to ensure data is valid at module boundaries.  
   • All function parameters are explicitly typed — never use bare `*args` or `**kwargs`.

4. **Full static safety.**  
   • `pyright --strict` must report zero errors; CI enforces this via `make lint types`.

5. **Keep the helpers façade thin.**  
   • `engine.py` is the only module that talks directly to the untyped `diplomacy` library. Keep it
     minimal and well-commented.

_Before every commit, run `make check-all` locally._

## 🐍 Coding guide for agents and humans

### 1 · Workflow

- Primary entry point: `make check-all` runs formatting, linting, type-checking, and tests. CI enforces same.
- One-off script: `uv run script.py` (never `python …`).

### 2 · Code & File Structure

- `diplomacy_agents/models.py`: Contains all Pydantic data models.
- `diplomacy_agents/types.py`: Contains all semantic type aliases (e.g., `type Order = str`).
- `diplomacy_agents/literals.py`: Contains all `typing.Literal` definitions for constrained value sets.
- Imports: All imports must be absolute and placed at the top of the file.
- Names: Use `snake_case` for variables and functions. Export public symbols via `__all__`.
- Simplicity: Keep code linear and obvious. Avoid clever one-liners or unnecessary branching. Use keyword-only arguments for clarity.

### 3 · Typing (`pyright --strict`)

- **Forbidden:** `Any`, `Optional` where a default is possible, unchecked reflection, and silent `# type: ignore` comments.
- **Single escape hatch:** `engine.py` is the only place `cast()` or `# type: ignore` may be used to handle the untyped `diplomacy` library.
- Prefer explicit types: Use `Literal`, `NewType`, and Pydantic models over raw primitives like `str` or `dict`.

### 4 · Contracts

- Validate external inputs at boundaries using Pydantic models.
- Favor immutability: use frozen Pydantic models or tuples for data you don't intend to mutate.
- Fail fast with clear exceptions; never use silent fallbacks.
