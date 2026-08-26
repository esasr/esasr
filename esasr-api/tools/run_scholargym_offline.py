#!/usr/bin/env python3
"""Build a local ScholarGym FTS5 index and evaluate a lexical baseline.

This runner deliberately makes no network or LLM calls. It provides a
deterministic, resumable baseline for validating the ScholarGym data and the
ESASR metric pipeline before running costlier agent ablations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.metrics import evaluate_cutoffs


STOPWORDS = {
    "a", "about", "an", "and", "any", "are", "as", "at", "based", "be",
    "been", "by", "can", "could", "do", "does", "for", "from", "has",
    "have", "how", "i", "in", "into", "is", "it", "me", "mention", "of",
    "on", "or", "paper", "papers", "please", "provide", "related", "research",
    "some", "studies", "study", "tell", "that", "the", "their", "there",
    "these", "they", "this", "through", "to", "use", "used", "using", "was",
    "were", "what", "when", "where", "which", "who", "with", "work", "works",
    "would", "you",
}
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_json_object(path: Path, chunk_size: int = 1024 * 1024) -> Iterator[tuple[str, dict]]:
    """Stream key/value pairs from a top-level JSON object using stdlib only."""
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as stream:
        buffer = ""
        position = 0
        eof = False

        def refill() -> bool:
            nonlocal buffer, position, eof
            if position:
                buffer = buffer[position:]
                position = 0
            block = stream.read(chunk_size)
            if not block:
                eof = True
                return False
            buffer += block
            return True

        def ensure() -> bool:
            while position >= len(buffer) and not eof:
                refill()
            return position < len(buffer)

        def skip_space() -> None:
            nonlocal position
            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position < len(buffer) or eof:
                    return
                refill()

        def decode_value():
            nonlocal position
            while True:
                try:
                    value, end = decoder.raw_decode(buffer, position)
                    position = end
                    return value
                except json.JSONDecodeError:
                    if eof or not refill():
                        raise

        refill()
        skip_space()
        if not ensure() or buffer[position] != "{":
            raise ValueError(f"{path} is not a top-level JSON object")
        position += 1
        while True:
            skip_space()
            if not ensure():
                raise ValueError(f"unexpected EOF in {path}")
            if buffer[position] == "}":
                return
            if buffer[position] == ",":
                position += 1
                skip_space()
            key = decode_value()
            if not isinstance(key, str):
                raise ValueError("paper database key must be a string")
            skip_space()
            if not ensure() or buffer[position] != ":":
                raise ValueError(f"missing ':' after paper ID {key}")
            position += 1
            skip_space()
            value = decode_value()
            if not isinstance(value, dict):
                raise ValueError(f"paper {key} must be an object")
            yield key, value


def build_index(paper_db: Path, index_path: Path, rebuild: bool = False) -> dict:
    if index_path.exists() and not rebuild:
        with sqlite3.connect(index_path) as connection:
            count = connection.execute("SELECT count(*) FROM papers_fts").fetchone()[0]
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("paper_db_sha256") == sha256(paper_db) and int(count) > 0:
            return {"papers": count, "reused": True, "seconds": 0.0}
        raise ValueError("existing index does not match paper database; pass --rebuild-index")

    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_suffix(index_path.suffix + ".building")
    if temporary.exists():
        temporary.unlink()
    started = time.perf_counter()
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            PRAGMA cache_size=-262144;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE VIRTUAL TABLE papers_fts USING fts5(
                arxiv_id UNINDEXED,
                title,
                abstract,
                published UNINDEXED,
                tokenize='porter unicode61 remove_diacritics 2'
            );
            """
        )
        batch: list[tuple[str, str, str, str]] = []
        count = 0
        for paper_id, paper in iter_json_object(paper_db):
            batch.append((
                str(paper.get("arxiv_id") or paper.get("id") or paper_id),
                str(paper.get("title") or ""),
                str(paper.get("abstract") or ""),
                str(paper.get("published") or paper.get("date") or ""),
            ))
            if len(batch) >= 1000:
                connection.executemany(
                    "INSERT INTO papers_fts(arxiv_id,title,abstract,published) VALUES (?,?,?,?)",
                    batch,
                )
                count += len(batch)
                batch.clear()
                if count % 25000 == 0:
                    connection.commit()
                    print(f"[index] {count:,} papers", flush=True)
        if batch:
            connection.executemany(
                "INSERT INTO papers_fts(arxiv_id,title,abstract,published) VALUES (?,?,?,?)",
                batch,
            )
            count += len(batch)
        connection.executemany(
            "INSERT INTO metadata(key,value) VALUES (?,?)",
            [
                ("paper_db_sha256", sha256(paper_db)),
                ("paper_count", str(count)),
                ("created_at", datetime.now(timezone.utc).isoformat()),
                ("retriever", "SQLite FTS5 BM25-compatible fielded index"),
            ],
        )
        connection.commit()
        connection.execute("INSERT INTO papers_fts(papers_fts) VALUES ('optimize')")
        connection.commit()
    finally:
        connection.close()
    temporary.replace(index_path)
    return {"papers": count, "reused": False, "seconds": time.perf_counter() - started}


def read_benchmark(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not any(row.get("gt_label") or []):
                continue
            row["_line"] = line_number
            rows.append(row)
    return rows


def stratified_sample(rows: list[dict], limit: int | None, seed: int) -> list[dict]:
    if limit is None or limit >= len(rows):
        return rows
    rng = random.Random(seed)
    by_source: dict[str, list[dict]] = {}
    for row in rows:
        by_source.setdefault(str(row.get("source") or "unknown"), []).append(row)
    allocation = {source: max(1, round(limit * len(group) / len(rows))) for source, group in by_source.items()}
    while sum(allocation.values()) > limit:
        source = max(allocation, key=lambda item: allocation[item])
        allocation[source] -= 1
    while sum(allocation.values()) < limit:
        source = max(by_source, key=lambda item: len(by_source[item]) - allocation[item])
        allocation[source] += 1
    selected = []
    for source, group in sorted(by_source.items()):
        selected.extend(rng.sample(group, min(allocation[source], len(group))))
    return sorted(selected, key=lambda row: row["_line"])


def query_tokens(text: str, maximum: int = 24) -> list[str]:
    tokens = []
    seen = set()
    for token in TOKEN_RE.findall(text.lower()):
        token = token.strip("_-")
        if len(token) < 2 or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= maximum:
            break
    return tokens


def retrieve(
    connection: sqlite3.Connection,
    query: str,
    before_date: str,
    top_k: int,
    title_weight: float,
    abstract_weight: float,
) -> list[dict]:
    tokens = query_tokens(query)
    if not tokens:
        return []
    match = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
    return retrieve_match(
        connection,
        match,
        before_date,
        top_k,
        title_weight,
        abstract_weight,
    )


def retrieve_match(
    connection: sqlite3.Connection,
    match: str,
    before_date: str,
    top_k: int,
    title_weight: float,
    abstract_weight: float,
) -> list[dict]:
    sql = (
        "SELECT arxiv_id,title,abstract,published,"
        f"bm25(papers_fts,0.0,{title_weight:g},{abstract_weight:g},0.0) AS score "
        "FROM papers_fts WHERE papers_fts MATCH ? "
    )
    params: list[object] = [match]
    if before_date:
        sql += "AND (published='' OR substr(published,1,7)<=?) "
        params.append(before_date[:7])
    sql += "ORDER BY score, arxiv_id LIMIT ?"
    params.append(top_k)
    return [
        {
            "arxivId": row[0],
            "title": row[1],
            "abstract": row[2],
            "published": row[3],
            "score": round(float(row[4]), 6),
        }
        for row in connection.execute(sql, params)
    ]


def rule_routes(query: str) -> list[dict]:
    """Create deterministic retrieval routes without LLM or API calls."""
    tokens = query_tokens(query)
    if not tokens:
        return []
    quoted = ['"' + token.replace('"', '""') + '"' for token in tokens]
    focused = sorted(tokens, key=lambda token: (-len(token), tokens.index(token)))[:4]
    return [
        {"name": "title", "match": "title : (" + " OR ".join(quoted) + ")"},
        {"name": "focused", "match": " AND ".join(f'"{token}"' for token in focused)},
    ]


def rrf_fuse(routes: list[tuple[str, float, list[dict]]], rrf_k: int) -> list[dict]:
    scores: dict[str, float] = {}
    papers: dict[str, dict] = {}
    sources: dict[str, list[str]] = {}
    for route_name, weight, rows in routes:
        if weight <= 0:
            continue
        for rank, paper in enumerate(rows, 1):
            paper_id = str(paper.get("arxivId") or "")
            if not paper_id:
                continue
            papers[paper_id] = paper
            scores[paper_id] = scores.get(paper_id, 0.0) + weight / (rrf_k + rank)
            sources.setdefault(paper_id, []).append(route_name)
    ordered = sorted(papers, key=lambda paper_id: (-scores[paper_id], paper_id))
    return [
        {
            **papers[paper_id],
            "rrfScore": round(scores[paper_id], 8),
            "retrievalRoutes": sources[paper_id],
        }
        for paper_id in ordered
    ]


def strip_abstracts(papers: list[dict]) -> list[dict]:
    return [{key: value for key, value in paper.items() if key != "abstract"} for paper in papers]


def to_gold(row: dict) -> dict:
    relevant = []
    labels = row.get("gt_label") or []
    for index, paper in enumerate(row.get("cited_paper") or []):
        label = labels[index] if index < len(labels) else 1
        if label:
            relevant.append({
                "arxivId": paper.get("arxiv_id"),
                "title": paper.get("title"),
                "year": paper.get("year"),
                "relevance": float(label),
            })
    return {
        "id": str(row.get("qid")),
        "query": row.get("query", ""),
        "source": row.get("source"),
        "dateCutoff": row.get("date"),
        "relevant": relevant,
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline ScholarGym lexical baseline")
    parser.add_argument("--paper-db", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=200, help="Stratified query count; 0 means all")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--retrieve-k", type=int, default=100)
    parser.add_argument(
        "--output-k",
        type=int,
        default=1,
        help="Number of papers in the precision-oriented final output",
    )
    parser.add_argument(
        "--title-weight",
        type=float,
        default=1.0,
        help="FTS5 BM25 title weight (validated default: 1.0)",
    )
    parser.add_argument("--abstract-weight", type=float, default=1.0)
    parser.add_argument("--retrieval-strategy", choices=("single", "rrf"), default="single")
    parser.add_argument("--rrf-k", type=int, default=30)
    parser.add_argument("--title-route-weight", type=float, default=0.1)
    parser.add_argument("--focused-route-weight", type=float, default=0.0)
    parser.add_argument("--route-k", type=int, default=50)
    parser.add_argument("--cross-encoder-model", default="")
    parser.add_argument("--cross-encoder-device", default="auto")
    parser.add_argument("--rerank-top-n", type=int, default=20)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--rebuild-index", action="store_true")
    args = parser.parse_args()
    if (
        args.limit < 0
        or args.retrieve_k < 1
        or not 1 <= args.output_k <= args.retrieve_k
        or args.title_weight <= 0
        or args.abstract_weight <= 0
        or args.rrf_k < 1
        or args.route_k < 1
        or not 1 <= args.rerank_top_n <= args.retrieve_k
    ):
        parser.error("limits must be non-negative and BM25 field weights must be positive")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    index_info = build_index(args.paper_db, args.index, args.rebuild_index)
    rows = stratified_sample(read_benchmark(args.benchmark), args.limit or None, args.seed)
    gold = [to_gold(row) for row in rows]
    predictions = []
    latencies = []
    rerank_latencies = []
    source_counts = Counter(row.get("source") for row in rows)
    reranker = None
    if args.cross_encoder_model:
        from services.reranker_service import CrossEncoderReranker

        reranker = CrossEncoderReranker(
            model_name=args.cross_encoder_model,
            batch_size=16,
            max_length=512,
            device=args.cross_encoder_device,
        )
    connection = sqlite3.connect(args.index)
    try:
        connection.execute("PRAGMA query_only=ON")
        for index, row in enumerate(rows, 1):
            started = time.perf_counter()
            papers = retrieve(
                connection,
                row.get("query", ""),
                row.get("date", ""),
                args.retrieve_k,
                args.title_weight,
                args.abstract_weight,
            )
            if args.retrieval_strategy == "rrf":
                routes: list[tuple[str, float, list[dict]]] = [("original", 1.0, papers)]
                for route in rule_routes(row.get("query", "")):
                    route_weight = (
                        args.title_route_weight
                        if route["name"] == "title"
                        else args.focused_route_weight
                    )
                    if route_weight <= 0:
                        continue
                    route_rows = retrieve_match(
                        connection,
                        route["match"],
                        row.get("date", ""),
                        args.route_k,
                        args.title_weight,
                        args.abstract_weight,
                    )
                    routes.append((route["name"], route_weight, route_rows))
                papers = rrf_fuse(routes, args.rrf_k)[: args.retrieve_k]

            rerank_started = time.perf_counter()
            if reranker is not None:
                prepared = [
                    {**paper, "relevanceScore": 1.0 / rank}
                    for rank, paper in enumerate(papers, 1)
                ]
                reranked = reranker.rerank(row.get("query", ""), prepared, args.rerank_top_n)
                reranked_ids = {paper.get("arxivId") for paper in reranked}
                papers = reranked + [paper for paper in prepared if paper.get("arxivId") not in reranked_ids]
            rerank_latency = (time.perf_counter() - rerank_started) * 1000
            rerank_latencies.append(rerank_latency)
            latency = (time.perf_counter() - started) * 1000
            latencies.append(latency)
            predictions.append({
                "id": str(row.get("qid")),
                "query": row.get("query", ""),
                "predicted": strip_abstracts(papers),
                "metrics": {
                    "apiCalls": 0,
                    "llmCalls": 0,
                    "totalTokens": 0,
                    "totalDurationMs": round(latency, 3),
                    "rerankDurationMs": round(rerank_latency, 3),
                    "failures": [],
                },
            })
            if index % 25 == 0 or index == len(rows):
                print(f"[retrieve] {index}/{len(rows)}", flush=True)
    finally:
        connection.close()

    cutoffs = sorted({k for k in (1, 2, 3, 5, 10, 20, 100) if k <= args.retrieve_k})
    reports = evaluate_cutoffs(
        gold,
        predictions,
        cutoffs,
        bootstrap_samples=args.bootstrap_samples,
        confidence=0.95,
        seed=args.seed,
    )
    write_jsonl(args.out_dir / "gold.jsonl", gold)
    write_jsonl(args.out_dir / "predictions.jsonl", predictions)
    write_jsonl(
        args.out_dir / "selected_predictions.jsonl",
        [{**row, "predicted": row["predicted"][: args.output_k]} for row in predictions],
    )
    (args.out_dir / "metrics.json").write_text(json.dumps({"cutoffs": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_selection = {
        "method": "proportional stratified sample",
        "queries": len(rows),
        "seed": args.seed,
        "sources": source_counts,
    }
    manifest = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "scope": "offline lexical baseline; not an official ScholarGym leaderboard score",
        "retriever": (
            "SQLite FTS5 BM25-compatible ranking, "
            f"title weight {args.title_weight:g}, abstract weight {args.abstract_weight:g}"
        ),
        "retrievalStrategy": {
            "name": args.retrieval_strategy,
            "rrfK": args.rrf_k if args.retrieval_strategy == "rrf" else None,
            "routeK": args.route_k if args.retrieval_strategy == "rrf" else None,
            "titleWeight": args.title_route_weight if args.retrieval_strategy == "rrf" else None,
            "focusedWeight": args.focused_route_weight if args.retrieval_strategy == "rrf" else None,
        },
        "reranker": {
            "enabled": reranker is not None,
            "model": args.cross_encoder_model,
            "topN": args.rerank_top_n if reranker is not None else 0,
            "device": args.cross_encoder_device if reranker is not None else "",
            "meanLatencyMs": round(sum(rerank_latencies) / len(rerank_latencies), 3),
        },
        "paperDb": {"path": str(args.paper_db), "sha256": sha256(args.paper_db), **index_info},
        "benchmark": {"path": str(args.benchmark), "sha256": sha256(args.benchmark)},
        "budget": {"apiCalls": 0, "llmCalls": 0, "tokens": 0, "retrieveK": args.retrieve_k},
        "selection": {
            **manifest_selection,
            "recommendedOutputK": args.output_k,
            "tuningProtocol": "field weight and output K selected on deterministic hash-split development subset",
        },
        "latencyMs": {
            "mean": round(sum(latencies) / len(latencies), 3),
            "p95": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 3),
        },
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for cutoff in cutoffs:
        report = reports[str(cutoff)]
        print(
            f"k={cutoff} macro P/R/F1={report['macro']['precision']:.4f}/"
            f"{report['macro']['recall']:.4f}/{report['macro']['f1']:.4f} "
            f"MAP={report['macro']['averagePrecision']:.4f} nDCG={report['macro']['ndcg']:.4f}"
        )
    print(f"results={args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
