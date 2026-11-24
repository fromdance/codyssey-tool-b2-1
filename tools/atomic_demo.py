"""저장 원자성(임시 파일 → rename 교체)을 눈으로 확인하는 데모 스크립트.

사용법 (프로젝트 폴더에서):
    python tools/atomic_demo.py ./demo
"""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from budget_app import storage                      # noqa: E402
from budget_app.services import BudgetService       # noqa: E402

data_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "./demo")
service = BudgetService(data_dir)
service.initialize()
tx_file = data_dir / "transactions.jsonl"


def show(title: str) -> None:
    print(f"\n--- {title}")
    for p in sorted(data_dir.glob("*transactions*")):
        print(f"  {p.name:<40} inode={p.stat().st_ino}  {p.stat().st_size}B")


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()[:12]


# [실험 1] 교체 직전 순간 포착: os.replace 를 가로채서 그 순간의 폴더 상태를 출력
real_replace = os.replace

def spy_replace(src: str, dst: str) -> None:
    show("os.replace 직전 (임시 파일과 원본이 함께 존재)")
    print(f"  원본 내용 TX-000001 amount: {first_amount()}  ← 아직 이전 값")
    real_replace(src, dst)

def first_amount():
    return next(t.amount for t in storage.TransactionRepository(tx_file).iter_all() if t.id == "TX-000001")

show("update 전")
storage.os.replace = spy_replace  # type: ignore[assignment]  # 데모용 가로채기
service.update_transaction("TX-000001", {"amount": 12345})
storage.os.replace = real_replace
show("update 후 (임시 파일 사라짐, inode 변경 = 새 파일로 교체됨)")
print(f"  TX-000001 amount: {first_amount()}")

# [실험 2] 다시 쓰는 도중 강제 실패 → 원본이 그대로인지 확인
print("\n=== 실험 2: 3번째 거래를 쓰는 중에 오류 발생시키기")
before = md5(tx_file)
count = 0

def crash(tx):
    global count
    count += 1
    if count == 3:
        raise RuntimeError("쓰기 도중 강제 중단!")
    return tx

try:
    service.transactions.rewrite(crash)
except RuntimeError as exc:
    print(f"  예외 발생: {exc}")
after = md5(tx_file)
show("실패 후")
print(f"  원본 해시 전/후: {before} / {after} → {'동일 (원본 무사)' if before == after else '변경됨!'}")