"""저장소 계층: 파일 입출력만 책임진다.

저장 포맷: JSONL (JSON Lines) — 한 줄에 JSON 객체 1개.
    {"id": "TX-000001", "type": "expense", "date": "2024-01-15", ...}
    {"id": "TX-000002", "type": "income",  "date": "2024-01-16", ...}
JSONL 을 고른 이유:
    - 한 줄씩 독립적이라 '한 줄 읽고 처리하고 버리는' 스트리밍에 딱 맞다.
    - 새 거래 추가는 파일 끝에 한 줄 덧붙이기(append)만 하면 된다.
    - 메모에 쉼표/줄바꿈이 있어도 JSON 이 알아서 이스케이프해 준다.

핵심 개념
    1) 제너레이터(yield): 파일 전체를 메모리에 올리지 않고 한 줄씩 꺼내 준다.
    2) 원자적 저장(atomic write): 임시 파일에 다 쓴 다음 os.replace() 로 한 번에 교체.
       → 쓰는 도중 프로그램이 죽어도 원본 파일은 '이전 상태' 그대로 남는다. (보너스 4)
"""

import json
import os
import tempfile
from collections.abc import Callable, Iterable, Iterator, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

from .errors import NotFoundError, StorageError, ValidationError
from .models import RC_PREFIX, TX_PREFIX, RecurringRule, Transaction, format_id, id_number


# ---------------------------------------------------------------------------
# 공통 파일 도우미
# ---------------------------------------------------------------------------
@contextmanager
def atomic_open(path: Path) -> Generator[TextIO]:
    """원자적으로 파일을 쓰기 위한 컨텍스트 매니저 (with 문에서 사용).

    사용법:
        with atomic_open(path) as f:
            f.write("...")
    동작 순서:
        1. 같은 폴더에 임시 파일(.transactions.jsonl.xxxx.tmp) 생성
        2. with 블록 안에서 임시 파일에 내용 쓰기
        3. 디스크에 확실히 기록(flush + fsync)
        4. os.replace(임시, 원본) — OS 가 '한 번에' 바꿔치기 해 준다(원자적 연산)
        5. 도중에 예외가 나면 임시 파일만 지우고 원본은 건드리지 않는다
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            yield f
            f.flush()
            os.fsync(f.fileno())
        # mkstemp 는 보안상 권한을 600(나만 읽기/쓰기)으로 만든다 → 원본 권한(없으면 644)으로 맞춤
        os.chmod(tmp_path, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """JSONL 파일을 한 줄씩 읽어 (줄 번호, dict) 를 하나씩 내보내는 제너레이터.

    `yield` 가 있는 함수는 호출해도 바로 실행되지 않고 '제너레이터 객체'를 돌려준다.
    for 문이 다음 값을 요청할 때마다 다음 yield 까지만 실행된다.
    → 100만 줄 파일이어도 메모리에는 '지금 처리 중인 한 줄'만 있다.
    """
    if not path.exists():
        return  # 파일이 없으면 아무것도 내보내지 않음(빈 제너레이터)
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):  # 파일 객체 자체가 '한 줄씩' 읽는 이터레이터
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                raise StorageError(
                    f"{path.name} 파일 {lineno}번째 줄이 손상되었습니다.",
                    "`backup restore` 로 복구하거나, 해당 줄을 직접 수정/삭제하세요.",
                ) from None
            yield lineno, record


def to_line(record: dict[str, Any]) -> str:
    """dict → JSONL 한 줄. ensure_ascii=False 로 한글을 그대로 저장."""
    return json.dumps(record, ensure_ascii=False) + "\n"


class JsonlTable:
    """작은 데이터(카테고리, 예산, 반복 규칙)용 저장소의 공통 부모 클래스.

    이런 데이터는 많아야 수십 줄이므로 통째로 읽고(load) 통째로 쓴다(save).
    쓰기는 항상 atomic_open 으로 안전하게 한다.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure_file(self) -> bool:
        """파일이 없으면 빈 파일 생성. 새로 만들었으면 True."""
        if self.path.exists():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        return True

    def load(self) -> list[dict[str, Any]]:
        return [record for _, record in iter_jsonl(self.path)]

    def save(self, records: Iterable[dict[str, Any]]) -> None:
        with atomic_open(self.path) as f:
            for record in records:
                f.write(to_line(record))


# ---------------------------------------------------------------------------
# 거래 저장소 (대용량 가능성이 있으므로 '스트리밍' 방식)
# ---------------------------------------------------------------------------
class TransactionRepository:
    """transactions.jsonl 을 다루는 저장소.

    - 읽기: iter_all() 제너레이터로 한 건씩 스트리밍
    - 추가: append (파일 끝에 덧붙이기)
    - 수정/삭제: 원본을 한 줄씩 읽으면서 임시 파일에 다시 쓰고 원자적 교체
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure_file(self) -> bool:
        if self.path.exists():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()
        return True

    # ---- 읽기 -------------------------------------------------------------
    def iter_all(self) -> Iterator[Transaction]:
        """모든 거래를 파일 순서대로 하나씩 내보낸다 (제너레이터)."""
        for lineno, record in iter_jsonl(self.path):
            try:
                yield Transaction.from_dict(record)
            except ValidationError as exc:
                raise StorageError(
                    f"{self.path.name} 파일 {lineno}번째 줄 데이터가 올바르지 않습니다: {exc.message}",
                    "`backup restore` 로 복구하거나, 해당 줄을 직접 수정하세요.",
                ) from None

    def get(self, tx_id: str) -> Transaction | None:
        # next(제너레이터, 기본값): 조건에 맞는 첫 번째 값을 찾으면 즉시 멈춘다(나머지는 읽지 않음)
        return next((tx for tx in self.iter_all() if tx.id == tx_id), None)

    def next_id(self) -> str:
        """현재 가장 큰 id 번호 + 1. max() 도 제너레이터를 한 건씩 소비하므로 메모리 절약."""
        last = max((id_number(tx.id) for tx in self.iter_all()), default=0)
        return format_id(TX_PREFIX, last + 1)

    # ---- 쓰기 -------------------------------------------------------------
    def append_many(self, transactions: Iterable[Transaction]) -> int:
        """여러 거래를 파일 끝에 추가. 추가한 개수를 반환."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with self.path.open("a", encoding="utf-8") as f:
            for tx in transactions:
                f.write(to_line(tx.to_dict()))
                count += 1
            f.flush()
            os.fsync(f.fileno())
        return count

    def append(self, tx: Transaction) -> None:
        self.append_many([tx])

    def rewrite(self, transform: Callable[[Transaction], Transaction | None]) -> int:
        """모든 거래에 transform 을 적용해 파일을 다시 쓴다 (원자적 교체).

        transform 반환값:
            같은 객체   → 그대로 유지
            새 객체     → 수정된 것으로 교체
            None        → 삭제
        반환: 바뀌거나 삭제된 건수

        원본 파일을 한 줄씩 읽으면서(스트리밍) 동시에 임시 파일에 한 줄씩 쓰므로
        파일이 아무리 커도 메모리는 거의 쓰지 않는다.
        """
        changed = 0
        with atomic_open(self.path) as out:
            for tx in self.iter_all():
                new_tx = transform(tx)
                if new_tx is not tx:
                    changed += 1
                if new_tx is not None:
                    out.write(to_line(new_tx.to_dict()))
        return changed

    def update(self, tx_id: str, transform: Callable[[Transaction], Transaction]) -> Transaction:
        if self.get(tx_id) is None:
            raise _not_found(tx_id)
        result: list[Transaction] = []

        def apply(tx: Transaction) -> Transaction:
            if tx.id != tx_id:
                return tx
            new_tx = transform(tx)
            result.append(new_tx)
            return new_tx

        self.rewrite(apply)
        return result[0]

    def delete(self, tx_id: str) -> Transaction:
        target = self.get(tx_id)
        if target is None:
            raise _not_found(tx_id)
        self.rewrite(lambda tx: None if tx.id == tx_id else tx)
        return target


def _not_found(tx_id: str) -> NotFoundError:
    return NotFoundError(
        f"id={tx_id} 거래를 찾을 수 없습니다 (없는 데이터).",
        "`list` 또는 `search` 명령으로 올바른 id 를 확인하세요.",
    )


# ---------------------------------------------------------------------------
# 카테고리 / 예산 / 반복 규칙 저장소
# ---------------------------------------------------------------------------
class CategoryStore(JsonlTable):
    """categories.jsonl — 한 줄에 {"name": "food"}"""

    def list_names(self) -> list[str]:
        return [str(r["name"]) for r in self.load() if "name" in r]

    def exists(self, name: str) -> bool:
        return name in self.list_names()

    def add(self, name: str) -> bool:
        """추가. 이미 있으면 False."""
        names = self.list_names()
        if name in names:
            return False
        self.save({"name": n} for n in [*names, name])
        return True

    def remove(self, name: str) -> None:
        names = self.list_names()
        if name not in names:
            raise NotFoundError(f"'{name}' 카테고리가 없습니다.", "`category list` 로 목록을 확인하세요.")
        self.save({"name": n} for n in names if n != name)


class BudgetStore(JsonlTable):
    """budgets.jsonl — 한 줄에 {"month": "2024-01", "amount": 500000}"""

    def all(self) -> dict[str, int]:
        return {str(r["month"]): int(r["amount"]) for r in self.load()}

    def get(self, month: str) -> int | None:
        return self.all().get(month)

    def set(self, month: str, amount: int) -> None:
        budgets = self.all()
        budgets[month] = amount  # 같은 달이 있으면 덮어쓰기(upsert)
        self.save({"month": m, "amount": a} for m, a in sorted(budgets.items()))


class RecurringStore(JsonlTable):
    """recurring.jsonl — 반복 내역 규칙 (보너스 2)."""

    def list_rules(self) -> list[RecurringRule]:
        rules: list[RecurringRule] = []
        for record in self.load():
            try:
                rules.append(RecurringRule.from_dict(record))
            except ValidationError as exc:
                raise StorageError(f"{self.path.name} 데이터가 올바르지 않습니다: {exc.message}") from None
        return rules

    def add(self, rule_without_id: dict[str, Any]) -> RecurringRule:
        rules = self.list_rules()
        next_no = max((id_number(r.id) for r in rules), default=0) + 1
        rule = RecurringRule.from_dict({**rule_without_id, "id": format_id(RC_PREFIX, next_no)})
        self.save(r.to_dict() for r in [*rules, rule])
        return rule

    def remove(self, rule_id: str) -> RecurringRule:
        rules = self.list_rules()
        target = next((r for r in rules if r.id == rule_id), None)
        if target is None:
            raise NotFoundError(f"id={rule_id} 반복 규칙을 찾을 수 없습니다.", "`recurring list` 로 id 를 확인하세요.")
        self.save(r.to_dict() for r in rules if r.id != rule_id)
        return target

    def replace_category(self, old: str, new: str) -> int:
        rules = self.list_rules()
        changed = sum(1 for r in rules if r.category == old)
        if changed:
            self.save(
                {**r.to_dict(), "category": new} if r.category == old else r.to_dict() for r in rules
            )
        return changed
