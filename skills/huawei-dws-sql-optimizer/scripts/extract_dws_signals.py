#!/usr/bin/env python3
"""Extract DWS execution-plan signals from stdin or a file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PATTERNS = {
    "redistribute": re.compile(r"Streaming\s*\(type:\s*REDISTRIBUTE\)", re.IGNORECASE),
    "broadcast": re.compile(r"Streaming\s*\(type:\s*BROADCAST\)", re.IGNORECASE),
    "gather": re.compile(r"Streaming\s*\(type:\s*GATHER\)", re.IGNORECASE),
    "remote_query": re.compile(r"Remote Query", re.IGNORECASE),
    "data_node_scan": re.compile(r"Data Node Scan", re.IGNORECASE),
    "seq_scan": re.compile(r"Seq Scan", re.IGNORECASE),
    "cstore_scan": re.compile(r"CStore Scan", re.IGNORECASE),
    "sort": re.compile(r"\bSort\b", re.IGNORECASE),
    "hash_aggregate": re.compile(r"HashAggregate|Hash Aggregate", re.IGNORECASE),
    "aggregate": re.compile(r"\bAggregate\b", re.IGNORECASE),
    "nested_loop": re.compile(r"Nested Loop", re.IGNORECASE),
}

TIME_PATTERN = re.compile(r"actual\s+time\s*=\s*([0-9.]+)\.\.([0-9.]+)", re.IGNORECASE)
ROWS_PATTERN = re.compile(r"rows\s*=\s*([0-9]+)")


def read_plan(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def build_summary(hits: dict[str, list[tuple[int, str]]]) -> list[dict[str, str]]:
    hypotheses: list[dict[str, str]] = []

    if hits["redistribute"]:
        hypotheses.append(
            {
                "issue": "可能存在重分布瓶颈",
                "evidence": f"发现 {len(hits['redistribute'])} 个 REDISTRIBUTE 节点",
                "next_action": "优先检查 JOIN/GROUP BY 键与分布键是否一致，评估是否需要 colocated join 或重分布。",
            }
        )
    if hits["broadcast"]:
        hypotheses.append(
            {
                "issue": "可能存在广播代价过高",
                "evidence": f"发现 {len(hits['broadcast'])} 个 BROADCAST 节点",
                "next_action": "确认被广播对象是否真的是小表，并检查统计信息是否过期。",
            }
        )
    if hits["gather"]:
        hypotheses.append(
            {
                "issue": "可能存在 CN Gather 瓶颈",
                "evidence": f"发现 {len(hits['gather'])} 个 GATHER 节点",
                "next_action": "考虑在 DN 侧先过滤、聚合或去重，减少回流到 CN 的数据量。",
            }
        )
    if hits["seq_scan"] or hits["cstore_scan"]:
        scan_count = len(hits["seq_scan"]) + len(hits["cstore_scan"])
        hypotheses.append(
            {
                "issue": "可能存在大表扫描或过滤下推不足",
                "evidence": f"发现 {scan_count} 个扫描热点节点",
                "next_action": "检查谓词是否可下推、是否命中分区裁剪，以及行存高选择性场景是否适合索引。",
            }
        )
    if hits["sort"] or hits["hash_aggregate"] or hits["aggregate"]:
        hypotheses.append(
            {
                "issue": "可能存在排序或聚合代价过高",
                "evidence": "执行计划中出现 Sort / Aggregate 热点",
                "next_action": "检查是否可以先过滤再排序/聚合，或先做局部聚合再汇总。",
            }
        )
    if hits["nested_loop"]:
        hypotheses.append(
            {
                "issue": "可能存在不合适的 Nested Loop",
                "evidence": f"发现 {len(hits['nested_loop'])} 个 Nested Loop 节点",
                "next_action": "确认 JOIN 两侧数据规模、数据类型和过滤位置，避免大表对大表 Nested Loop。",
            }
        )

    return hypotheses


def to_payload(
    hits: dict[str, list[tuple[int, str]]],
    hottest: list[tuple[float, int, str]],
    max_lines: int,
) -> dict[str, object]:
    return {
        "counts": {label: len(items) for label, items in sorted(hits.items())},
        "highlights": {
            label: [
                {"line": lineno, "text": text, "rows": int(match.group(1)) if (match := ROWS_PATTERN.search(text)) else None}
                for lineno, text in items[:max_lines]
            ]
            for label, items in hits.items()
            if items
        },
        "hottest_lines": [
            {"line": lineno, "end_time": end_time, "text": text}
            for end_time, lineno, text in sorted(hottest, reverse=True)[:10]
        ],
        "hypotheses": build_summary(hits),
    }


def print_markdown(payload: dict[str, object], max_lines: int) -> None:
    counts = payload["counts"]
    highlights = payload["highlights"]
    hottest_lines = payload["hottest_lines"]
    hypotheses = payload["hypotheses"]

    print("# DWS plan signals")
    print()
    print("## Operator counts")
    for label, count in counts.items():
        print(f"- {label}: {count}")

    print()
    print("## Highlighted lines")
    if not highlights:
        print("- No tracked DWS signals were found.")
        print()
    else:
        ordered_labels = [
            "redistribute",
            "broadcast",
            "gather",
            "remote_query",
            "data_node_scan",
            "seq_scan",
            "cstore_scan",
            "nested_loop",
            "sort",
            "hash_aggregate",
            "aggregate",
        ]
        for label in ordered_labels:
            items = highlights.get(label)
            if not items:
                continue
            print(f"### {label}")
            for item in items[:max_lines]:
                row_info = f" | rows={item['rows']}" if item["rows"] is not None else ""
                print(f"- L{item['line']}: {item['text']}{row_info}")
            print()

    if hypotheses:
        print("## Quick hypotheses")
        for item in hypotheses:
            print(f"- {item['issue']}：{item['evidence']}；下一步：{item['next_action']}")
        print()

    if hottest_lines:
        print("## Hottest lines by end time")
        for item in hottest_lines:
            print(f"- L{item['line']}: end_time={item['end_time']:.3f} | {item['text']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract DWS plan signals for long EXPLAIN output")
    parser.add_argument("path", nargs="?", help="Optional plan text file path")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    parser.add_argument("--max-lines", type=int, default=8, help="Maximum highlighted lines per operator")
    args = parser.parse_args()

    plan = read_plan(args.path)
    if not plan.strip():
        print("No plan text provided.", file=sys.stderr)
        return 1

    hits: dict[str, list[tuple[int, str]]] = defaultdict(list)
    hottest: list[tuple[float, int, str]] = []

    for lineno, line in enumerate(plan.splitlines(), start=1):
        stripped = line.strip()
        for label, pattern in PATTERNS.items():
            if pattern.search(stripped):
                hits[label].append((lineno, stripped))
        time_match = TIME_PATTERN.search(stripped)
        if time_match:
            end_time = float(time_match.group(2))
            hottest.append((end_time, lineno, stripped))

    payload = to_payload(hits, hottest, max_lines=args.max_lines)
    if args.json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_markdown(payload, max_lines=args.max_lines)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
