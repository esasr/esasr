#!/usr/bin/env python3
"""Run reproducible ESASR ablations on a frozen ScholarGym pilot set."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.llm_service import plan_search_query, plan_search_query_uncached
from services.scholar_service import search_papers
from services.search_pipeline import SearchBudget, run_search_pipeline, search_semantic_scholar


CONFIGS = {
    "A": {
        "description": "single planned query, OpenAlex only, no second round",
        "budget": SearchBudget(1, 15, 1, "none"),
        "sources": ("OpenAlex",),
    },
    "C0": {
        "description": "two planned queries, two sources, no second round",
        "budget": SearchBudget(4, 15, 4, "none"),
        "sources": ("OpenAlex", "Semantic Scholar"),
    },
    "C1": {
        "description": "two sources with a fixed planned second round",
        "budget": SearchBudget(4, 15, 8, "fixed"),
        "sources": ("OpenAlex", "Semantic Scholar"),
    },
    "D": {
        "description": "two sources with coverage-gap-driven second round",
        "budget": SearchBudget(4, 15, 8, "coverage"),
        "sources": ("OpenAlex", "Semantic Scholar"),
    },
}


async def search_openalex_strict(query: str, limit: int) -> list[dict]:
    """Never substitute demo papers into an experimental run."""
    return await search_papers(query, limit, fallback_on_error=False)


async def search_semantic_scholar_strict(query: str, limit: int) -> list[dict]:
    """Propagate exhausted rate limits into the experiment failure log."""
    return await search_semantic_scholar(query, limit, raise_on_error=True)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def combine_plan_attempts(attempts: list[dict], delivered: dict) -> dict:
    usage_fields = ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens")
    combined = {
        field: sum(int((attempt.get("usage") or {}).get(field, 0) or 0) for attempt in attempts)
        for field in usage_fields
    }
    delivered["usage"] = combined
    delivered["planningAttempts"] = len(attempts)
    delivered["planningFailedAttempts"] = sum(bool(attempt.get("fallbackReason")) for attempt in attempts)
    delivered["attemptUsage"] = [
        {
            "plannerMode": attempt.get("plannerMode"),
            "fallbackReason": attempt.get("fallbackReason"),
            "usage": attempt.get("usage") or {},
        }
        for attempt in attempts
    ]
    return delivered


def select_pilot(rows: list[dict], per_source: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    selected: list[dict] = []
    for source in ("PASA_AutoScholar", "LitSearch", "PASA_RealScholar"):
        candidates = [row for row in rows if row.get("valid") and row.get("source") == source]
        if len(candidates) < per_source:
            raise ValueError(f"not enough valid rows for {source}: {len(candidates)}")
        selected.extend(rng.sample(candidates, per_source))
    return sorted(selected, key=lambda row: str(row.get("qid")))


def to_gold(row: dict) -> dict:
    labels = row.get("gt_label") or []
    relevant = []
    for index, paper in enumerate(row.get("cited_paper") or []):
        label = labels[index] if index < len(labels) else 1
        if label:
            relevant.append(
                {
                    "arxivId": paper.get("arxiv_id"),
                    "title": paper.get("title"),
                    "year": paper.get("year"),
                    "relevance": float(label),
                }
            )
    return {
        "id": str(row.get("qid")),
        "query": row.get("query", ""),
        "split": "scholargym-pilot",
        "domain": "computer-science",
        "language": "en",
        "difficulty": "pilot",
        "source": row.get("source"),
        "dateCutoff": row.get("date"),
        "relevant": relevant,
    }


def git_state(root: Path) -> dict:
    def run(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        ).stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
        "dirtyFiles": run("status", "--short").splitlines(),
    }


async def freeze_plans(
    gold: list[dict],
    path: Path,
    provider: str | None,
    model: str | None,
    *,
    fresh_plans: bool = False,
) -> dict[str, dict]:
    existing = {row["id"]: row["plan"] for row in read_jsonl(path)} if path.exists() else {}
    planner = plan_search_query_uncached if fresh_plans else plan_search_query
    for index, row in enumerate(gold, start=1):
        query_id = row["id"]
        if query_id in existing:
            continue
        started = time.perf_counter()
        plan = await planner(row["query"], provider, model)
        attempts = [plan]
        if plan.get("fallbackReason"):
            await asyncio.sleep(0.5)
            retry = await planner(row["query"], provider, model)
            attempts.append(retry)
            if not retry.get("fallbackReason"):
                plan = retry
        plan = combine_plan_attempts(attempts, plan)
        plan["experimentPlanningDurationMs"] = round((time.perf_counter() - started) * 1000)
        append_jsonl(path, {"id": query_id, "query": row["query"], "plan": plan})
        existing[query_id] = plan
        print(
            f"[plan {index}/{len(gold)}] {query_id}: {plan.get('plannerMode')} "
            f"tokens={plan.get('usage', {}).get('total_tokens', 0)}",
            flush=True,
        )
    return existing


async def run_config(
    name: str,
    spec: dict,
    gold: list[dict],
    plans: dict[str, dict],
    output: Path,
    *,
    retry_failures: bool = False,
    only_ids: set[str] | None = None,
) -> None:
    existing_rows = read_jsonl(output) if output.exists() else []
    existing = {row["id"]: row for row in existing_rows}
    completed = {
        query_id
        for query_id, row in existing.items()
        if not retry_failures or not row.get("metrics", {}).get("failures")
    }
    available_retrievers = {
        "OpenAlex": search_openalex_strict,
        "Semantic Scholar": search_semantic_scholar_strict,
    }
    retrievers = {source: available_retrievers[source] for source in spec["sources"]}

    for index, row in enumerate(gold, start=1):
        query_id = row["id"]
        if only_ids and query_id not in only_ids:
            continue
        if query_id in completed:
            continue
        result = await run_search_pipeline(
            query=row["query"],
            limit=20,
            budget=spec["budget"],
            retrievers=retrievers,
            reranker_metadata={
                "status": "disabled",
                "model": "",
                "detail": "Pilot A-D isolates retrieval strategy before Cross Encoder evaluation.",
            },
            plan_override=plans[query_id],
        )
        result["id"] = query_id
        result["predicted"] = result.pop("papers")
        result["constraints"] = result.get("plan", {}).get("constraints", {})
        result["experiment"] = {"config": name, "description": spec["description"]}
        if any(str(paper.get("id", "")).startswith(("local_", "mock_")) for paper in result["predicted"]):
            result["metrics"].setdefault("failures", []).append("offline fallback detected")
        existing[query_id] = result
        write_jsonl(output, [existing[item["id"]] for item in gold if item["id"] in existing])
        print(
            f"[{name} {index}/{len(gold)}] {query_id}: papers={len(result['predicted'])} "
            f"calls={result['metrics']['apiCalls']} latency={result['metrics']['totalDurationMs']}ms "
            f"failures={len(result['metrics'].get('failures', []))}",
            flush=True,
        )


async def main_async(args: argparse.Namespace) -> int:
    benchmark_rows = read_jsonl(args.benchmark)
    pilot_rows = select_pilot(benchmark_rows, args.per_source, args.seed)
    gold = [to_gold(row) for row in pilot_rows]
    if any(not row["relevant"] for row in gold):
        raise ValueError("pilot contains a query without a positive gold paper")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    gold_path = args.out_dir / "gold.jsonl"
    if gold_path.exists() and read_jsonl(gold_path) != gold:
        raise ValueError("existing gold.jsonl differs; choose a new output directory")
    write_jsonl(gold_path, gold)

    project_root = Path(__file__).resolve().parents[2]
    benchmark_hash = hashlib.sha256(args.benchmark.read_bytes()).hexdigest()
    try:
        benchmark_manifest_path = str(args.benchmark.resolve().relative_to(project_root.resolve()))
    except ValueError:
        benchmark_manifest_path = str(args.benchmark.resolve())

    manifest = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": "ScholarGym",
            "path": benchmark_manifest_path,
            "sha256": benchmark_hash,
            "selection": "stratified random sample without replacement",
            "perSource": args.per_source,
            "seed": args.seed,
            "queries": len(gold),
        },
        "provider": args.provider,
        "model": args.model,
        "plannerCachePolicy": "bypassed" if args.fresh_plans else "production-cache",
        "configurations": {
            name: {
                "description": CONFIGS[name]["description"],
                "sources": CONFIGS[name]["sources"],
                "budget": CONFIGS[name]["budget"].__dict__,
            }
            for name in args.config
        },
        "git": git_state(project_root),
        "integrityNote": "Pilot results are real live-API runs; they are not full-benchmark or competition scores.",
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    plans = await freeze_plans(
        gold,
        args.out_dir / "plans.jsonl",
        args.provider,
        args.model,
        fresh_plans=args.fresh_plans,
    )
    for name in args.config:
        await run_config(
            name,
            CONFIGS[name],
            gold,
            plans,
            args.out_dir / f"predictions_{name}.jsonl",
            retry_failures=args.retry_failures,
            only_ids=set(args.only_id or []),
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a ScholarGym-based live API pilot.")
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--per-source", type=int, default=3)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--config", action="append", choices=sorted(CONFIGS), help="Repeat; default A,C0,C1,D")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument(
        "--fresh-plans",
        action="store_true",
        help="Bypass the query-plan cache while retaining production heuristic routing.",
    )
    parser.add_argument("--only-id", action="append", help="Run only a selected query id; repeat as needed")
    args = parser.parse_args()
    args.config = args.config or ["A", "C0", "C1", "D"]
    if args.per_source < 1:
        parser.error("--per-source must be positive")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
