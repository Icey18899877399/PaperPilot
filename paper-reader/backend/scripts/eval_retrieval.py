"""US-04 检索质量评测脚本：对运行中的后端跑一组问题，计算命中率与MRR。

对齐验收标准"检索测试能够展示召回片段及相关度"：给定若干"问题→期望页码"，
逐题调用 GET /api/papers/{id}/search，统计：

- Hit@k（成功率@k）：前k条召回中至少命中一个期望页码的题目占比；
- MRR：首个命中结果排名的倒数的平均值。

用法（后端需先启动）::

    # 用内置参考评测集（面向 2025.coling-main.353 OpenForecast）自动选一篇已解析论文
    python scripts/eval_retrieval.py

    # 指定论文与外部评测集（JSON：[{"question": "...", "expected_pages": [6]}, ...]）
    python scripts/eval_retrieval.py --paper-id <id> --eval-file my_eval.json --k 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 内置参考评测集（面向英文论文 2025.coling-main.353 OpenForecast）。
#
# 重要：评测问题的语言应与论文正文语言一致。当前 US-04 采用关键词 + 本地
# TF-IDF 向量的词面检索，无法跨语言匹配（中文问题问英文论文会大面积零召回）。
# 因此本参考集用英文关键词问题；期望页码取自论文真实章节位置（ground truth）。
# 若要评测中文问题→英文论文的跨语言检索，需先启用 embedding 后端
# （配置 EMBEDDING_API_URL，见 config.py），或换用中文论文 + 中文问题评测集。
DEFAULT_EVAL: list[dict] = [
    {"question": "dataset construction, collection and statistics", "expected_pages": [3, 4, 5]},
    {"question": "event timeline annotation two-stage pipeline", "expected_pages": [3, 4]},
    {"question": "LRAE retrieval-augmented evaluation method", "expected_pages": [5]},
    {"question": "experimental setup, baseline models and metrics", "expected_pages": [6]},
    {"question": "main results on open-ended tasks and F1", "expected_pages": [6, 7]},
    {"question": "limitations of this work", "expected_pages": [9]},
]


def pick_ready_paper(base_url: str, client: httpx.Client) -> str | None:
    papers = client.get(f"{base_url}/api/papers", timeout=15).json()
    for paper in papers:
        if paper.get("status") == "ready":
            return paper["id"]
    return None


def evaluate(base_url: str, paper_id: str, eval_set: list[dict], k: int) -> None:
    max_k = max(k, 5)
    hit_at = {1: 0, 3: 0, 5: 0}
    reciprocal_ranks: list[float] = []
    rows: list[str] = []

    with httpx.Client(trust_env=False) as client:
        for case in eval_set:
            question = case["question"]
            expected = set(case["expected_pages"])
            resp = client.get(
                f"{base_url}/api/papers/{paper_id}/search",
                params={"q": question, "limit": max_k},
                timeout=30,
            )
            resp.raise_for_status()
            items = resp.json()["items"]
            pages = [item["page"] for item in items]

            first_hit_rank = next(
                (rank for rank, page in enumerate(pages, start=1) if page in expected),
                None,
            )
            reciprocal_ranks.append(1.0 / first_hit_rank if first_hit_rank else 0.0)
            for threshold in hit_at:
                if any(page in expected for page in pages[:threshold]):
                    hit_at[threshold] += 1

            mark = f"命中@{first_hit_rank}" if first_hit_rank else "未命中"
            rows.append(
                f"  [{mark:>6}] 期望页{sorted(expected)} | 召回页{pages[:k]}\n"
                f"           {question}"
            )

    total = len(eval_set)
    print(f"论文ID：{paper_id}    题目数：{total}")
    print("-" * 68)
    print("\n".join(rows))
    print("-" * 68)
    for threshold in (1, 3, 5):
        print(f"命中率@{threshold}（Hit@{threshold}）：{hit_at[threshold] / total:.1%}")
    print(f"MRR：{sum(reciprocal_ranks) / total:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="US-04 检索质量评测（命中率与MRR）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--paper-id", default=None, help="缺省时自动选一篇已解析论文")
    parser.add_argument("--eval-file", type=Path, default=None, help="外部评测集JSON")
    parser.add_argument("--k", type=int, default=5, help="展示的召回条数")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    eval_set = (
        json.loads(args.eval_file.read_text(encoding="utf-8"))
        if args.eval_file
        else DEFAULT_EVAL
    )

    with httpx.Client(trust_env=False) as client:
        paper_id = args.paper_id or pick_ready_paper(base_url, client)
    if not paper_id:
        print("找不到已解析（ready）的论文，请先上传并解析一篇，或用 --paper-id 指定。")
        raise SystemExit(1)

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    evaluate(base_url, paper_id, eval_set, args.k)


if __name__ == "__main__":
    main()
