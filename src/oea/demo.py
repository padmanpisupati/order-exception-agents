"""Run the governed exception workflow over open orders and print an operational summary.

Usage: python -m oea.demo [--data PATH] [--limit N] [--no-langgraph]
"""
from __future__ import annotations
import argparse
import json
import time
from collections import Counter
from pathlib import Path

from .audit import AuditLog
from .data import load_dataco
from .erp import MockERP
from .graph import build_workflow, run_case
from .hitl import SimulatedApprover
from .llm import RuleBasedLLM

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "sample" / "dataco_synthetic_sample.csv"
REAL = ROOT / "data" / "raw" / "DataCoSupplyChainDataset.csv"


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-langgraph", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "out")
    a = ap.parse_args(argv)
    path = a.data or (REAL if REAL.exists() else SAMPLE)
    synthetic = path == SAMPLE
    orders = load_dataco(path, limit=a.limit)
    erp, audit = MockERP(orders), AuditLog(a.out / "audit.jsonl")
    app, engine = build_workflow(erp, RuleBasedLLM(), SimulatedApprover(), audit,
                              use_langgraph=not a.no_langgraph)
    t0, results, lat = time.perf_counter(), [], []
    for o in orders:
        t = time.perf_counter()
        results.append(run_case(app, o.order_item_id))
        lat.append((time.perf_counter() - t) * 1e3)
    outs = [x for r in results for x in r["outcomes"]]
    status = Counter(x["status"] for x in outs)
    by_exc = Counter(x["exception"] for x in outs)
    val = Counter()
    for x in outs:
        val[x["status"]] += x.get("value_at_stake", 0)
    lat.sort()
    summary = {
        "dataset": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        "synthetic_data": synthetic, "engine": engine,
        "open_orders_processed": len(orders),
        "orders_with_exceptions": sum(1 for r in results if r["outcomes"]),
        "exception_outcomes": len(outs),
        "by_exception": dict(by_exc), "by_status": dict(status),
        "value_at_stake_by_status": {k: round(v, 2) for k, v in val.items()},
        "touchless_rate": round(status["auto_executed"] / len(outs), 3) if outs else 0,
        "erp_writes": len(erp.write_log),
        "audit_records": len(audit.records), "audit_chain_valid": audit.verify(),
        "latency_ms_p50": round(lat[len(lat) // 2], 2) if lat else 0,
        "latency_ms_p95": round(lat[int(len(lat) * 0.95) - 1], 2) if lat else 0,
        "wall_s": round(time.perf_counter() - t0, 2),
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if synthetic:
        print("\nNOTE: SYNTHETIC sample data. Figures demonstrate mechanics, not real outcomes.")
    return summary


if __name__ == "__main__":
    main()
