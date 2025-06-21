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

GitHub Actions runs `make lint` and `make types` for every push & PR.

### Tooling

All config (ruff, pyright) lives in `pyproject.toml`. Makefile is self-documenting:

```bash
make help
```
