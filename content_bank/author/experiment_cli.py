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


def _merge_eval(acc, book_eval, name):
    """Fold one book's evaluator report into the cross-book accumulator (union of
    per-unit results + summed aggregate counters under runs[name])."""
    src = (book_eval.get("runs") or {}).get(name) or {}
    dst = acc["runs"][name]
    dst["units"].update(src.get("units") or {})
    for k, v in (src.get("aggregate") or {}).items():
        dst["aggregate"][k] = dst["aggregate"].get(k, 0) + v


def _run_fit_evaluation(out, name, groups, evaluator_route, sink):
    """Run the deterministic + D1-D8-fit evaluator per book on an experiment's
    drafts and merge into one cross-book evaluator report. ``groups`` is
    ``{book: units | None}``; drafts are read from ``out/<book>/runs/<name>/``.

    Only units that actually produced a draft are evaluated — a unit that failed
    to build (gates never came clean) has no draft file, so it is skipped here
    rather than raising; the failure is already recorded in the build result."""
    eval_report = {"runs": {name: {"units": {}, "aggregate": {}}}}
    for book, units in groups.items():
        drafts_dir = out / book / "runs" / name / "drafts"
        present = ({p.stem for p in drafts_dir.glob("*.json")}
                   if drafts_dir.is_dir() else set())
        if units is None:
            eval_units = None  # whole book -> evaluate every draft present
        else:
            eval_units = [u for u in units if u in present]
            if not eval_units:
                continue
        book_eval = quality_eval.evaluate(
            book, [name], units=eval_units, base=out,
            evaluator_route=evaluator_route, sink=sink)
        _merge_eval(eval_report, book_eval, name)
    return eval_report


def run_experiment(config_path, *, out_root=_DEFAULT_OUT_ROOT, resume=False,
                   now, corpus_rev):
    """Execute one experiment; write its result tree; return the manifest dict.
    ``now`` (ISO timestamp) and ``corpus_rev`` are injected so the core is
    deterministic and unit-testable."""
    config = experiment_config.load(config_path)
    experiment_config.validate(config)
    name = config["name"]
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

    # Group work by book (single-book config -> one group; cross-book config ->
    # one group per BOOK- prefix). Each book builds into its own nested run dir; a
    # single shared sink + gate_trace_dir span every book.
    groups = experiment_config.books_and_units(config)
    dim_cap = int(gates_cfg.get("dim_cap", gates.DEFAULT_DIM_CAP))
    max_repair = int(gates_cfg.get("max_repair", 2))

    snap_before = _subscription_snapshot()
    build_result = {"ok": [], "failed": {}}
    for book, units in groups.items():
        run_rel = pathlib.Path(book) / "runs" / name
        _seed_run_manifest(book, out / run_rel / "manifest.json", units)
        res = build_cli.run(
            book, units=units, routes=routes, review_on=True,
            max_repair=max_repair, dim_cap=dim_cap,
            manifest_path=out / run_rel / "manifest.json",
            drafts_dir=out / run_rel / "drafts",
            briefs_dir=out / run_rel / "briefs",
            verdicts_dir=out / run_rel / "verdicts",
            gate_trace_dir=out / "gate_traces",
            sink=sink, experiment=name)
        build_result["ok"].extend(res.get("ok", []))
        build_result["failed"].update(res.get("failed", {}))
    eval_report = _run_fit_evaluation(out, name, groups, evaluator_route, sink)
    snap_after = _subscription_snapshot()

    report = experiment_report.build_report(
        out, eval_report=eval_report, draft_route=routes.draft,
        evaluator_route=evaluator_route)
    (out / "report.json").write_text(
        json.dumps({"experiment": name, "books": sorted(groups),
                    "metrics": report, "evaluator_report": eval_report},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "name": name,
        "book": config.get("book"),
        "books": sorted(groups),
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


_DEFAULT_TRANSLATE = {"backend": "llm_core", "model": "deepseek-v4-flash"}


def translate_experiment(name, *, out_root=_DEFAULT_OUT_ROOT, concurrency=4):
    """Translate an experiment's English drafts into CUV-aligned Chinese proposals.

    Uses the config's ``translate`` (and optional ``drift``) route — defaulting to
    the standard translator (deepseek-v4-flash) when unset — walks every book in
    the experiment, writes proposals under each book's run dir, and appends per-call
    telemetry to the experiment's shared calls.jsonl. Proposals stay draft-only;
    promotion to the store remains a separate, human-gated step."""
    from . import glossary as _glossary, translate_cli
    from .build_cli import _run_slug

    out = pathlib.Path(out_root) / name
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    config = manifest["config"]
    translate_route = Route.from_json(config.get("translate") or _DEFAULT_TRANSLATE)
    drift_route = (Route.from_json(config["drift"]) if config.get("drift")
                   else translate_route)
    slug = _run_slug(translate_route.backend, translate_route.model)
    sink = TelemetrySink(out / "calls.jsonl")
    glossary = _glossary.load_glossary()

    summary = {}
    for book in manifest.get("books") or ([manifest["book"]] if manifest.get("book") else []):
        drafts_dir = out / book / "runs" / name / "drafts"
        if not drafts_dir.is_dir():
            continue
        items = translate_cli.load_drafts(drafts_dir)
        proposals = translate_cli.run_proposals(
            items, book, glossary=glossary, route=translate_route,
            drift_route=drift_route, concurrency=concurrency, sink=sink)
        out_dir = drafts_dir.parent / "translations" / slug
        translate_cli.write_proposals(proposals, out_dir)
        summary[book] = {"proposals": len(proposals), "items": len(items),
                         "dir": str(out_dir)}
    return {"experiment": name, "translate_model": translate_route.model,
            "drift_model": drift_route.model, "books": summary}


def evaluate_experiment(name, *, out_root=_DEFAULT_OUT_ROOT, fit=False,
                        fit_route=None, units=None):
    """Report over an existing experiment. By default just re-aggregates the
    persisted telemetry (no LLM calls). With ``fit=True`` it runs the D1-D8
    classification-fit evaluator on the experiment's drafts using ``fit_route``
    (an independent judge) — or the config's ``evaluator`` when unset — on the
    given ``units`` (or every unit), rewrites report.json, and returns the metrics.
    This is how an imported baseline gets fit-scored by the same judge as another
    experiment for a fair classification-error comparison."""
    out = pathlib.Path(out_root) / name
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    routes = RouteConfig.from_experiment(manifest["config"]["routes"])
    evaluator_route = fit_route or Route.from_json(manifest["config"]["evaluator"])
    if not fit:
        return experiment_report.build_report(
            out, draft_route=routes.draft, evaluator_route=evaluator_route)

    if units:
        groups = {}
        for uid in units:
            groups.setdefault(experiment_config.book_of_unit(uid), []).append(uid)
    else:
        groups = {b: None for b in _experiment_books(out)}
    sink = TelemetrySink(out / "calls.jsonl")
    eval_report = _run_fit_evaluation(out, name, groups, evaluator_route, sink)
    report = experiment_report.build_report(
        out, eval_report=eval_report, draft_route=routes.draft,
        evaluator_route=evaluator_route)
    (out / "report.json").write_text(
        json.dumps({"experiment": name, "books": sorted(groups),
                    "metrics": report, "evaluator_report": eval_report},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _experiment_books(exp_dir):
    """Books an experiment covers, from its manifest (books list or single book)."""
    manifest = json.loads((exp_dir / "manifest.json").read_text(encoding="utf-8"))
    return manifest.get("books") or ([manifest["book"]] if manifest.get("book") else [])


def _experiment_has_book(exp_dir, book):
    name = exp_dir.name
    return (exp_dir / book / "runs" / name / "drafts").is_dir()


def _compare_filename(kind, names, books):
    """A single output filename reflecting the compared experiments (and books when
    a subset is requested): kind_<name1>__<name2>[__<book1>-<book2>].html, with the
    experiment list collapsed to '<first>__and_N_more' if it would be too long."""
    joined = "__".join(names)
    if len(joined) > 80:
        joined = f"{names[0]}__and_{len(names) - 1}_more"
    tail = f"__{'-'.join(books)}" if len(books) == 1 else ""
    return f"{kind}_{joined}{tail}.html"


def _books_across(dirs, book):
    """Resolve the book set to render for a compare call: the explicit book, else
    every book found across the experiment dirs (sorted)."""
    if book:
        return [book]
    found = set()
    for d in dirs:
        found.update(_experiment_books(d))
    return sorted(found)


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
    p_eval.add_argument("--fit", action="store_true",
                        help="run the D1-D8 classification-fit evaluator (LLM calls)")
    p_eval.add_argument("--fit-backend", choices=("llm_core", "claude"),
                        help="override the evaluator backend (independent judge)")
    p_eval.add_argument("--fit-model", help="override the evaluator model")
    p_eval.add_argument("--units", nargs="*",
                        help="limit the fit evaluation to these unit ids")

    p_tr = sub.add_parser("translate", help="translate an experiment's drafts to ZH")
    p_tr.add_argument("name")
    p_tr.add_argument("--out-root", default=_DEFAULT_OUT_ROOT)
    p_tr.add_argument("--concurrency", type=int, default=4)

    p_cmp = sub.add_parser("compare", help="render an experiment-column comparison")
    p_cmp.add_argument("--book", help="limit to one book; omit to emit one page per "
                       "book found across the experiments")
    p_cmp.add_argument("--experiments", required=True,
                       help="comma-separated experiment names")
    p_cmp.add_argument("--out-root", default=_DEFAULT_OUT_ROOT)
    p_cmp.add_argument("--out", help="output HTML path (single-book only)")

    p_ctr = sub.add_parser("compare-translations",
                           help="render EN/CUV/zh review across experiments")
    p_ctr.add_argument("--book", help="limit to one book; omit for all books found")
    p_ctr.add_argument("--experiments", required=True,
                       help="comma-separated experiment names")
    p_ctr.add_argument("--out-root", default=_DEFAULT_OUT_ROOT)
    p_ctr.add_argument("--out", help="output HTML path (single-book only)")

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
        fit_route = (Route(a.fit_backend or "llm_core", a.fit_model)
                     if (a.fit_backend or a.fit_model) else None)
        rep = evaluate_experiment(a.name, out_root=a.out_root, fit=a.fit,
                                  fit_route=fit_route, units=a.units)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "translate":
        res = translate_experiment(a.name, out_root=a.out_root,
                                   concurrency=a.concurrency)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if a.cmd in ("compare", "compare-translations"):
        from . import compare_html, translate_compare_html
        names = [n for n in a.experiments.split(",") if n]
        dirs = [pathlib.Path(a.out_root) / n for n in names]
        books = _books_across(dirs, a.book)
        if not books:
            print("Nothing to compare (no books found across the experiments).")
            return 0
        kind = "compare" if a.cmd == "compare" else "compare_translations"
        if a.cmd == "compare":
            html = compare_html.render_experiments(books, dirs)
        else:
            html = translate_compare_html.render_experiment_translations(books, dirs)
        default = f"{a.out_root}/{_compare_filename(kind, names, books)}"
        out_path = pathlib.Path(a.out or default)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(f"Wrote {out_path}  ({len(names)} experiments, {len(books)} books: "
              f"{', '.join(books)})")
        return 0
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
