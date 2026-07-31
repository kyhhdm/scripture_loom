"""Named content-pipeline experiment runner (#35).

Executes the real builder pipeline (same gates + review semantics) under an
explicit per-stage RouteConfig, retains normalized call telemetry and gate
traces, runs the deterministic + D1-D8-fit evaluator on a fixed evaluator route,
and writes a self-contained, immutable result tree under ``experiments-out/NAME``.

Commands::

    experiment_cli validate experiments/NAME.json
    experiment_cli run experiments/NAME.json [--resume]
    experiment_cli evaluate NAME
    experiment_cli compare --book PHP --experiments NAME_A,NAME_B

The runner never publishes drafts (they stay draft-only, human-gated) and never
puts credentials in config or results.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess

from . import build_cli, experiment_config, experiment_report, gates, quality_eval
from .routing import Route, RouteConfig
from .telemetry import TelemetrySink

_DEFAULT_OUT_ROOT = "experiments-out"
_CANON_BUILD_ROOT = pathlib.Path("work/content_bank_build")


def _subscription_snapshot() -> dict:
    """Best-effort, pluggable account-usage snapshot. The individual Claude CLI
    exposes per-call usage but no documented machine-readable remaining-allowance
    endpoint, so this honestly records unavailability rather than scraping."""
    return {
        "available": False,
        "reason": "no documented machine-readable Claude subscription allowance; "
                  "per-call usage is captured in calls.jsonl instead",
    }


def _corpus_rev() -> str:
    """Git revision of the committed corpus canon (or 'unknown')."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD:corpus/canon"],
            capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _route_matrix(config: dict) -> dict:
    matrix = {stage: {"backend": r.get("backend"), "model": r.get("model")}
              for stage, r in config["routes"].items()}
    ev = config["evaluator"]
    matrix["evaluate"] = {"backend": ev.get("backend"), "model": ev.get("model")}
    return matrix


def _seed_run_manifest(book, manifest_path, units):
    """Create the run's stage ledger from the canonical book manifest if absent
    (so --resume keeps progress; a fresh run starts all-pending)."""
    from . import manifest as manifest_mod
    manifest_path = pathlib.Path(manifest_path)
    if manifest_path.exists():
        return
    canonical = manifest_mod.load(_CANON_BUILD_ROOT / book / "manifest.json")
    pericopes = [u for u, meta in canonical["units"].items()
                 if meta["kind"] == "pericope"]
    sections = [u for u, meta in canonical["units"].items()
                if meta["kind"] == "section"]
    m = manifest_mod.init_manifest(book, pericopes, sections)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_mod.save(manifest_path, m)


def run_experiment(config_path, *, out_root=_DEFAULT_OUT_ROOT, resume=False,
                   now, corpus_rev):
    """Execute one experiment; write its result tree; return the manifest dict.
    ``now`` (ISO timestamp) and ``corpus_rev`` are injected so the core is
    deterministic and unit-testable."""
    config = experiment_config.load(config_path)
    experiment_config.validate(config)
    name, book = config["name"], config["book"]
    config_hash = experiment_config.config_hash(
        config, corpus_rev=corpus_rev,
        prompt_version=experiment_config.PROMPT_VERSION)

    out = pathlib.Path(out_root) / name
    manifest_path = out / "manifest.json"
    existing = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else None)
    experiment_config.check_immutable(existing, config_hash)
    out.mkdir(parents=True, exist_ok=True)

    routes = RouteConfig.from_experiment(config["routes"])
    evaluator_route = Route.from_json(config["evaluator"])
    gates_cfg = config.get("gates") or {}
    sink = TelemetrySink(out / "calls.jsonl")

    run_rel = pathlib.Path(book) / "runs" / name
    run_manifest_path = out / run_rel / "manifest.json"
    if not resume and run_manifest_path.exists():
        # A fresh (non-resume) run of an identical config re-seeds cleanly.
        pass
    _seed_run_manifest(book, run_manifest_path, config.get("units"))

    snap_before = _subscription_snapshot()
    build_result = build_cli.run(
        book, units=config.get("units"), routes=routes, review_on=True,
        max_repair=int(gates_cfg.get("max_repair", 2)),
        dim_cap=int(gates_cfg.get("dim_cap", gates.DEFAULT_DIM_CAP)),
        manifest_path=run_manifest_path,
        drafts_dir=out / run_rel / "drafts",
        briefs_dir=out / run_rel / "briefs",
        verdicts_dir=out / run_rel / "verdicts",
        gate_trace_dir=out / "gate_traces",
        sink=sink, experiment=name)
    snap_after = _subscription_snapshot()

    eval_report = quality_eval.evaluate(
        book, [name], units=config.get("units"), base=out,
        evaluator_route=evaluator_route, sink=sink)

    report = experiment_report.build_report(
        out, eval_report=eval_report, draft_route=routes.draft,
        evaluator_route=evaluator_route)
    (out / "report.json").write_text(
        json.dumps({"experiment": name, "book": book, "metrics": report,
                    "evaluator_report": eval_report},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "name": name,
        "book": book,
        "config": config,
        "config_hash": config_hash,
        "corpus_rev": corpus_rev,
        "prompt_version": experiment_config.PROMPT_VERSION,
        "created_at": now,
        "route_matrix": _route_matrix(config),
        "subscription_before": snap_before,
        "subscription_after": snap_after,
        "build_result": build_result,
        "aggregate": {k: report[k] for k in (
            "calls_total", "claude_calls", "tokens_in_total", "tokens_out_total",
            "estimated_cost", "first_pass_gate_rate", "final_gate_rate",
            "evaluator_is_drafter")},
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def evaluate_experiment(name, *, out_root=_DEFAULT_OUT_ROOT):
    """Re-run reporting over an existing experiment out dir (no LLM calls beyond
    telemetry already captured); returns the metrics dict."""
    out = pathlib.Path(out_root) / name
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    routes = RouteConfig.from_experiment(manifest["config"]["routes"])
    evaluator_route = Route.from_json(manifest["config"]["evaluator"])
    return experiment_report.build_report(
        out, draft_route=routes.draft, evaluator_route=evaluator_route)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Named content-pipeline experiments")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="validate a config file")
    p_val.add_argument("config")

    p_run = sub.add_parser("run", help="run an experiment")
    p_run.add_argument("config")
    p_run.add_argument("--resume", action="store_true")
    p_run.add_argument("--out-root", default=_DEFAULT_OUT_ROOT)

    p_eval = sub.add_parser("evaluate", help="rebuild the report for an experiment")
    p_eval.add_argument("name")
    p_eval.add_argument("--out-root", default=_DEFAULT_OUT_ROOT)

    p_cmp = sub.add_parser("compare", help="render an experiment-column comparison")
    p_cmp.add_argument("--book", required=True)
    p_cmp.add_argument("--experiments", required=True,
                       help="comma-separated experiment names")
    p_cmp.add_argument("--out-root", default=_DEFAULT_OUT_ROOT)
    p_cmp.add_argument("--out", help="output HTML path")

    a = ap.parse_args(argv)
    if a.cmd == "validate":
        experiment_config.validate(experiment_config.load(a.config))
        print(f"OK: {a.config} is a valid experiment configuration")
        return 0
    if a.cmd == "run":
        man = run_experiment(a.config, out_root=a.out_root, resume=a.resume,
                             now=_now(), corpus_rev=_corpus_rev())
        print(f"Done: experiment {man['name']} -> {a.out_root}/{man['name']}")
        return 0
    if a.cmd == "evaluate":
        rep = evaluate_experiment(a.name, out_root=a.out_root)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "compare":
        from . import compare_html
        names = [n for n in a.experiments.split(",") if n]
        dirs = [pathlib.Path(a.out_root) / n for n in names]
        html = compare_html.render_experiments(a.book, dirs)
        out_path = pathlib.Path(a.out or f"{a.out_root}/compare_{a.book}.html")
        out_path.write_text(html, encoding="utf-8")
        print(f"Wrote {out_path}")
        return 0
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
