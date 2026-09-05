# Streak Keeper

Automated commit queue and daily streak keeper daemon.

## Architecture

Streak Keeper runs as a background daemon designed to preserve continuous commit activity on GitHub. It operates through an SQLite-backed queue and connects directly to the GitHub REST API.

### Key Components

- `scheduler.py`: Background cron-style scheduler that checks queue items and triggers scheduled commits or daily fallbacks.
- `github_client.py`: Lightweight GitHub REST API client supporting both single-file updates and multi-file tree commits with custom author dates and timezone offsets.
- `streak_db.py`: SQLite storage layer managing pending queue items, execution history, and runtime settings.
- `fallback_generator.py`: Generates clean, deterministic technical telemetry and diagnostic logs when the queue is empty at the end of the day.

## Features

- Timezone-aware commit scheduling (America/Sao_Paulo, UTC-3).
- Dual execution mode: scheduled queue items or automated fallback.
- Activity detection: verifies public and private commit activity via GitHub Search API to skip unnecessary commits when work was already pushed.
- Minimal resource consumption (~20MB RAM, 0% CPU under PM2).

## Deployment

```bash
pip install -r requirements.txt
export GITHUB_TOKEN="your_personal_access_token"
bash start.sh
```
