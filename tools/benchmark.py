"""대용량 성능 시뮬레이션: 거래 N건을 만들어 주요 작업의 실행 시간(과 최대 메모리)을 잰다.

사용법 (프로젝트 폴더에서):
    python tools/benchmark.py                 # 10만 건, 시간만 측정
    python tools/benchmark.py 300000 --mem    # 30만 건, 최대 메모리도 측정 (tracemalloc 때문에 느려짐)

임시 폴더에서 실행하고 끝나면 지우므로 실제 data 폴더는 건드리지 않는다.
"""

import argparse
import json
import random
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from budget_app.formatter import pad  # noqa: E402
from budget_app.services import BudgetService, SearchCriteria  # noqa: E402

CATEGORIES = ["food", "transport", "rent", "shopping", "etc"]


def generate(path: Path, count: int) -> None:
    rng = random.Random(42)  # 시드 고정 → 매번 같은 데이터
    with path.open("w", encoding="utf-8") as f:
        for i in range(1, count + 1):
            f.write(json.dumps({
                "id": f"TX-{i:06d}",
                "type": rng.choice(["income", "expense", "expense", "expense"]),
                "date": f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                "amount": rng.randint(1000, 99999),
                "category": rng.choice(CATEGORIES),
                "memo": rng.choice(["점심", "택시", "커피", "월세", ""]),
                "tags": [],
            }, ensure_ascii=False) + "\n")


def measure(name: str, func: Callable[[], object], with_memory: bool) -> None:
    start = time.perf_counter()
    func()
    elapsed = time.perf_counter() - start
    line = f"{pad(name, 32)} {elapsed:7.2f}s"  # pad: 한글 폭을 고려한 정렬
    if with_memory:
        tracemalloc.start()
        func()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        line += f"   peak {peak / 1024:8.0f} KB"
    print(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="budget_app 대용량 성능 시뮬레이션")
    parser.add_argument("count", type=int, nargs="?", default=100_000, help="생성할 거래 수 (기본 100000)")
    parser.add_argument("--mem", action="store_true", help="최대 메모리도 측정")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        service = BudgetService(data_dir)
        service.initialize()
        generate(service.transactions.path, args.count)
        size_mb = service.transactions.path.stat().st_size / 1e6
        print(f"거래 {args.count:,}건 / 파일 {size_mb:.1f}MB\n")

        mid = f"TX-{args.count // 2:06d}"
        measure("list --limit 20", lambda: service.latest(20), args.mem)
        measure("search --category food", lambda: service.search(SearchCriteria(category="food"), 20), args.mem)
        measure("search (limit 없음, 전체 정렬)", lambda: service.search(SearchCriteria(category="food")), args.mem)
        measure("summary --month 2024-03", lambda: service.monthly_summary("2024-03", 3), args.mem)
        measure("add (next_id 계산 포함)", lambda: service.add_transaction(
            tx_type="expense", date="2024-03-01", category="food", amount=100), args.mem)
        measure("update (파일 전체 재작성)", lambda: service.update_transaction(mid, {"amount": 1}), args.mem)


if __name__ == "__main__":
    main()