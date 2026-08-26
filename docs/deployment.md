# Deployment (Docker)

```
docker/
  api/
    Dockerfile                    # image build (context = project root)
  compose/
    docker-compose-sys-01.yaml    # service definition
  env/
    .env                          # local config, gitignored
    .env.example                  # committed template
```

The only docker-related file outside this tree is `.dockerignore` at the project root - Docker
requires it there since it must live at the build **context** root, not next to the Dockerfile
(context is the project root; see `context: ../..` in the compose file).

<details open>
<summary><strong>Run it</strong></summary>

From the project root:

```bash
cp docker/env/.env.example docker/env/.env   # first time only
docker compose --env-file docker/env/.env -f docker/compose/docker-compose-sys-01.yaml up -d --build
curl http://localhost:8000/health
```

Stop it with:

```bash
docker compose -f docker/compose/docker-compose-sys-01.yaml down
```

</details>

<details>
<summary><strong>Why the image is small despite a multi-GB dataset</strong></summary>

The image (~480MB) contains only Python + dependencies + `src/` - no data. `data/` is
bind-mounted **read-only** into the container at `/app/data` (see the `volumes:` entry in the
compose file), matching the path `src/config.py` already resolves paths against. This means:

- Rebuilding `data/bookfather.db` on the host (`python -m src.db.build_db`) is instantly visible
  to the running container - no image rebuild needed.
- The container cannot write to the dataset - confirmed with `docker exec bookfather-api touch
  /app/data/x` -> `Read-only file system`. The API only ever reads (`repository.get_connection()`
  opens SQLite in `mode=ro`), so this costs nothing functionally.
- `logs/` is mounted read-write so the container's rotating log files land on the host, next to
  the ones written by the CLI scripts when run outside Docker.

</details>

<details>
<summary><strong>Configuration</strong></summary>

`docker/env/.env` (gitignored; copy from `docker/env/.env.example`) currently controls one thing:
`API_PORT`, the host port the service is published on (container always listens on `8000`
internally). It's passed explicitly via `--env-file` (rather than relying on Compose's
auto-discovery, which looks in the invocation directory) since it now lives under `docker/`
rather than the project root. Add more keys here as the app grows.

</details>

<details>
<summary><strong>A bug this setup caught</strong></summary>

Running under FastAPI/uvicorn (as opposed to the raw dev-server smoke tests earlier in the
project) surfaced a real concurrency bug: `sqlite3.ProgrammingError: SQLite objects created in a
thread can only be used in that same thread`. FastAPI runs sync `yield`-style dependencies
through anyio's threadpool, which can hand the setup and teardown halves of `get_db()` to
different worker threads. Fixed in
[`repository.get_connection()`](../src/api/repository.py) with `check_same_thread=False` - safe
here because each connection is opened and closed within a single request's lifecycle and never
shared across requests. Verified against 25 concurrent requests with no errors in
`docker logs bookfather-api`.

</details>
