# Vendor mxlens's synchronous LLM core into scripture_loom

- **Date:** 2026-07-20
- **Branch / commits:** `feature/llm-core-vendor`; PR #17 (MERGED, merge commit `d435af8`); feature commit message `feat(llm_core): vendor mxlens sync LLM core; adopt uv (issue #16 prep)`
- **Summary:** Preparation for issue #16 (standalone content-bank builder): gave scripture_loom an in-process `llm()` capability by vendoring the minimal synchronous LLM path out of the mxlens service, adopting `uv`, and dropping the stdlib-only invariant.

## Request

The user opened by pointing at issue #16 and saying "first step I will add a llm service as preparation," then asked to read the mxlens repo at `/media/pb/data/testbed/mxlens_service/mxlens` ("which contains a llm rest api service") and "transport it into this project." The scope and shape of that transport were worked out interactively.

## What we did

- **Investigated both sides.** Issue #16 wants to replace the Claude Code agent workflow that builds the content library with a standalone Python program whose only non-deterministic steps are two templated LLM calls (brief, draft) + a repair loop; every other step is already a pure function. The scripture_loom seam is clean: `build_brief_prompt.build` → LLM → `build_draft_prompt.build` → LLM → gates (`schema.validate_item`, `quote_check.check`) → `store_writer.upsert_items`. On the mxlens side, the "LLM REST API service" is `POST /api/v1/llm/batch` — **async** (Celery task on a Redis `llm` queue, poll `/tasks/{id}`), deeply coupled to FastAPI/Celery/Redis/LiteLLM, default model `doubao-1.8`.
- **Worked through the architecture decision interactively.** Key realizations surfaced and steered the design: the repo was stdlib-only (conflicting with the service's deps); the only LLM endpoint is async (poll loop); and — decisive — `LLMService.run_batch_sync` is the shared core of *both* the Celery task and the mxlens "analyst" seam, which calls it **synchronously, in-process** via `run_sync_llm` / `run_batch_llm` (no Celery/Redis/REST).
- **Owner decisions along the way:** adopt `uv` and drop stdlib-only; reuse mxlens's `.env`; default model `deepseek-v4-flash` (not Claude); and — the final pivot — **Option B: vendor the light sync core** in-process, rather than run mxlens as a live HTTP service or add the anthropic SDK. Installing all of mxlens was ruled out (it drags torch/faiss/duckdb/mxdb + a private package index); lazy imports mean the sync path only needs `litellm`, `langchain-*`, `structlog`, `pydantic`/`pydantic-settings`, `tiktoken`.
- **Vendored the sync core** into a new top-level `llm_core/` package (chatmodels LiteLLM path + `run_batch_sync` + the analyst `run_sync_llm`/`run_batch_llm` + schemas/errors), rewired imports `mxlens.*`/`mxapi.*` → `llm_core.*`, trimmed the menu to LiteLLM/Fake, dropped the async `submit_batch` and the Redis cache, and guarded a stray `celery.exceptions` import in `batch_llm`.
- **Handled the key credential gotcha:** `chatmodels` reads `ARK_API_KEY` straight from `os.environ`, and a pydantic Settings object doesn't populate `os.environ` — so `llm_core/config.py` loads the `.env` into the real environment at import.
- **Made it self-contained** on user request: copied just `ARK_API_KEY` into a git-ignored repo-local `.env` (added `.env.example`, gitignored `.env`), and repointed the config default away from the absolute mxlens path.
- **Adopted uv, updated docs, committed, opened + merged PR #17.**

## Artifacts

- **New package `llm_core/`** — `__init__.py`, `sync.py`, `service.py`, `config.py` (new trimmed settings), `schemas.py`, `errors.py`, `chatmodels/` (`__init__`, `menu`, `basemodel`, `basechain`, `LiteLLM`, `_aio_runner`, `fakemodel`), `tests/test_sync.py`, `PROVENANCE.md` (records source commit `dc980f0` + every modification).
- **`content_bank/author/llm.py`** — the mockable `llm(prompt) -> text` seam issue #16 will call; `content_bank/tests/test_llm_seam.py`.
- **`pyproject.toml`** + **`uv.lock`** (uv, non-packaged project); **`.env.example`** (tracked); **`.env`** (git-ignored, holds `ARK_API_KEY`).
- **Edited:** `CLAUDE.md` (dropped stdlib-only invariant, documented uv + `llm_core` + the `.env`/`ARK_API_KEY` requirement); `.gitignore` (`.venv/`, `.env`).
- **Plan file:** `/home/pb/.claude/plans/read-issue-16-first-ethereal-forest.md`.

## Outcome

Merged to `main` via PR #17. Verified:
- Network-free unit tests (LLM seam mocked): `llm_core` 4/4, content_bank seam 1/1.
- Real call: `run_sync_llm('', 'Reply with one word: pong')` → `'pong'` via deepseek-v4-flash (repo-local `.env`, with parent-env `ARK_API_KEY` unset).
- Real authoring path: `build_brief_prompt.build('MAT-001')` → `llm()` → a 2352-char theological brief on Matthew 1:1-17.
- Regressions under uv: corpus 67, content_bank 129, prototype 34 — all green.

## Follow-ups

- Issue #16's `content_bank/author/build_cli.py`: manifest iteration, brief→draft→gates→repair loop, the new `refs_in_range` gate, rate-limit backoff, per-unit failure isolation, and staging items as `reviewed`.
- `llm_core` keeps some `mxlens`/`mxapi`/"analyst" mentions in docstrings/comments/logger names (left for traceability); optional cleanup later.
- No automated upstream re-sync from mxlens; `PROVENANCE.md` documents the manual re-copy procedure.
- Minor: some `git` commands were intermittently blocked by the auto-mode classifier this session; a Bash permission rule for `git commit`/`git push` would smooth future runs.
