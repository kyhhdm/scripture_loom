# llm_core provenance

`llm_core/` is **vendored** from the mxlens service — the minimal *synchronous,
in-process* LLM path, with the FastAPI / Celery / Redis / REST layers left
behind. It gives scripture_loom a `run_sync_llm` / `run_batch_llm` seam
(default model `deepseek-v4-flash`, Volcengine via LiteLLM) with no running
server. See issue #16 for why (a standalone content-bank builder needs a plain
`llm()` call, not the agent workflow).

## Source

- Repo: `mxlens` (MxLens API Service), local path
  `/media/pb/data/testbed/mxlens_service/mxlens`
- Commit: `dc980f0ca36545ebdeaa61d0e419dd0f9ff58bce` (`v2.0.0-999-gdc980f0`, 2026-07-17)

## Vendored files (source → here)

| mxlens source | llm_core |
|---|---|
| `mxapi/chatmodels/{__init__,menu,basemodel,basechain,LiteLLM,_aio_runner,fakemodel}.py` | `llm_core/chatmodels/` |
| `mxlens/services/llm_service.py` | `llm_core/service.py` |
| `mxlens/services/analyst/llm.py` | `llm_core/sync.py` |
| `mxlens/models/llm_schemas.py` | `llm_core/schemas.py` |
| `mxlens/utils/errors.py` | `llm_core/errors.py` |

New in llm_core (not from mxlens): `config.py` (trimmed settings + `.env`
loader), `__init__.py`, `tests/`.

## Modifications applied

- **Imports rewritten**: `mxlens.config` → `llm_core.config`,
  `mxlens.services.llm_service` → `llm_core.service`,
  `mxlens.models.llm_schemas` → `llm_core.schemas`,
  `mxlens.utils.errors` → `llm_core.errors`, `mxapi.chatmodels` →
  `llm_core.chatmodels` (incl. the `importlib` `package=` strings).
- **`chatmodels/menu.py`**: `_CLASS_MODULES` trimmed to `LiteLLM2Chat` +
  `Fake2Chat` (BedRock/OpenAi/native-Volcengine/claudeapi provider modules were
  not vendored). Model menu unchanged (all active entries are LiteLLM/Volcengine).
- **`service.py`**: dropped the async `submit_batch` method (Celery
  `run_llm_batch` + `task_service` + `queue_load`); dropped the Redis completion
  cache (`cache=True` now degrades to no-cache). `run_batch_sync` + `estimate`
  are unchanged in behavior.
- **`chatmodels/LiteLLM.py`**: `batch_llm`'s `from celery.exceptions import
  SoftTimeLimitExceeded` guarded with a never-matching sentinel when celery is
  absent (runs identically without Celery). The `gevent` import in
  `_aio_runner.py` was already `try/except`-guarded upstream.
- **`config.py`** (new): only the fields the sync path reads; default model
  `deepseek-v4-flash`; Redis cache off; loads the `.env` into `os.environ` so
  `chatmodels`' direct `ARK_API_KEY` reads work (path via
  `SCRIPTURE_LOOM_LLM_ENV`, default = this repo's git-ignored `.env`; the
  `ARK_API_KEY` value was copied from the mxlens `.env`).

Docstrings/comments/logger names may still reference `mxlens`/`mxapi`/the
"analyst" — left as-is to preserve traceability to the source above.

## Re-syncing

There is no automated sync. To pull upstream fixes, re-copy the files above from
the source repo and re-apply the modifications (they are small and localized).
