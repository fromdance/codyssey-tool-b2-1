"""서비스 계층: '가계부가 무엇을 할 수 있는가'(비즈니스 로직)를 책임진다.

    CLI(화면) ──호출──▶ BudgetService(규칙/계산) ──호출──▶ Repository/Store(파일)

- 화면에 무엇을 어떻게 찍을지는 모른다 (그건 cli/formatter 의 일).
- 파일을 어떻게 읽고 쓰는지도 모른다 (그건 storage 의 일).
- "카테고리가 등록돼 있어야 거래를 추가할 수 있다", "사용 중 카테고리는 함부로 못 지운다"
  같은 규칙과, 합계/TOP N 같은 계산만 담당한다.
"""

import csv
import heapq
import shutil
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from .errors import AppError, NotFoundError, StorageError, ValidationError
from .models import (
    RecurringRule,
    Transaction,
    format_id,
    id_number,
    month_range,
    parse_amount,
    parse_category_name,
    parse_date,
    parse_tags,
    parse_type,
    TX_PREFIX,
)
from .storage import BudgetStore, CategoryStore, RecurringStore, TransactionRepository, atomic_open

DEFAULT_CATEGORIES: tuple[str, ...] = ("food", "transport", "rent", "shopping", "salary", "allowance", "etc")
CSV_COLUMNS: tuple[str, ...] = ("date", "type", "category", "amount", "memo", "tags")
CSV_REQUIRED: tuple[str, ...] = ("date", "type", "category", "amount")


# ---------------------------------------------------------------------------
# 결과/조건을 담는 작은 데이터 클래스들
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SearchCriteria:
    """검색 조건. None 인 조건은 '검사하지 않음'."""

    date_from: str | None = None
    date_to: str | None = None
    category: str | None = None
    tx_type: str | None = None
    keyword: str | None = None
    tag: str | None = None

    def matches(self, tx: Transaction) -> bool:
        # 'YYYY-MM-DD' 문자열은 사전순 비교 = 날짜순 비교 (자릿수가 고정이라 가능)
        if self.date_from and tx.date < self.date_from:
            return False
        if self.date_to and tx.date > self.date_to:
            return False
        if self.category and tx.category != self.category:
            return False
        if self.tx_type and tx.type != self.tx_type:
            return False
        if self.keyword and self.keyword.lower() not in tx.memo.lower():
            return False
        if self.tag and self.tag not in tx.tags:
            return False
        return True


@dataclass(frozen=True)
class MonthlySummary:
    month: str
    income: int
    expense: int
    count: int
    top_categories: list[tuple[str, int]]
    budget: int | None

    @property
    def balance(self) -> int:
        return self.income - self.expense

    @property
    def usage_pct(self) -> float | None:
        if not self.budget:
            return None
        return self.expense / self.budget * 100

    @property
    def over_budget(self) -> int:
        """예산 초과 금액 (초과 안 했으면 0)."""
        return max(0, self.expense - self.budget) if self.budget else 0


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    created: list[Transaction] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 서비스
# ---------------------------------------------------------------------------
class BudgetService:
    DATA_FILES: tuple[str, ...] = ("transactions.jsonl", "categories.jsonl", "budgets.jsonl", "recurring.jsonl")

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.transactions = TransactionRepository(data_dir / "transactions.jsonl")
        self.categories = CategoryStore(data_dir / "categories.jsonl")
        self.budgets = BudgetStore(data_dir / "budgets.jsonl")
        self.recurring = RecurringStore(data_dir / "recurring.jsonl")
        self.backup_root = data_dir / "backups"

    # ---- 초기화 -----------------------------------------------------------
    def initialize(self) -> list[str]:
        """저장 폴더/파일이 없으면 만든다. 사용자에게 보여줄 안내 문구 목록을 반환."""
        notices: list[str] = []
        try:
            if not self.data_dir.exists():
                self.data_dir.mkdir(parents=True)
                notices.append(f"데이터 폴더를 새로 만들었습니다: {self.data_dir}")
            created = [
                store.path.name
                for store in (self.transactions, self.categories, self.budgets, self.recurring)
                if store.ensure_file()
            ]
        except OSError as exc:
            raise StorageError(
                f"데이터 폴더를 준비할 수 없습니다: {self.data_dir} ({exc.strerror})",
                "--datadir 로 쓰기 가능한 다른 폴더를 지정하세요.",
            ) from None
        if created:
            notices.append(f"저장 파일을 생성했습니다: {', '.join(created)}")
        # 정책(안 A): 카테고리가 비어 있으면 기본 카테고리 자동 생성
        if not self.categories.list_names():
            self.categories.save({"name": n} for n in DEFAULT_CATEGORIES)
            notices.append(f"기본 카테고리를 생성했습니다: {', '.join(DEFAULT_CATEGORIES)}")
        return notices

    # ---- 거래 CRUD --------------------------------------------------------
    def require_category(self, name: str) -> None:
        names = self.categories.list_names()
        if name not in names:
            raise ValidationError(
                f"등록되지 않은 카테고리입니다: {name}",
                f"등록된 카테고리: {', '.join(names) or '(없음)'} / 새로 만들려면 `category add`",
            )

    def add_transaction(
        self, *, tx_type: str, date: str, category: str, amount: int, memo: str = "", tags: tuple[str, ...] = ()
    ) -> Transaction:
        self.require_category(category)
        tx = Transaction(
            id=self.transactions.next_id(),
            type=tx_type, date=date, amount=amount, category=category, memo=memo, tags=tags,
        )
        self.transactions.append(tx)
        return tx

    def latest(self, limit: int) -> list[Transaction]:
        """최신순 상위 limit 건.

        heapq.nlargest 는 제너레이터를 한 건씩 받아 '상위 limit 개'만 기억한다.
        → 전체가 100만 건이어도 메모리에는 limit 개만 유지된다.
        """
        return heapq.nlargest(limit, self.transactions.iter_all(), key=Transaction.sort_key)

    def iter_matching(self, criteria: SearchCriteria) -> Iterator[Transaction]:
        """조건에 맞는 거래만 흘려보내는 '제너레이터 표현식' (아직 아무것도 읽지 않은 상태)."""
        return (tx for tx in self.transactions.iter_all() if criteria.matches(tx))

    def search(self, criteria: SearchCriteria, limit: int | None = None) -> list[Transaction]:
        matched = self.iter_matching(criteria)
        if limit is not None:
            return heapq.nlargest(limit, matched, key=Transaction.sort_key)
        # 제한이 없으면 '조건에 맞는 것들만' 정렬 (파일 전체가 아니라 결과만 메모리에 올라감)
        return sorted(matched, key=Transaction.sort_key, reverse=True)

    def update_transaction(self, tx_id: str, changes: dict[str, object]) -> Transaction:
        """changes 예: {"amount": 20000, "memo": "저녁"}  (dataclass 필드 이름 기준)"""
        if not changes:
            raise ValidationError("수정할 항목이 없습니다.", "--date, --type, --category, --amount, --memo, --tags 중 1개 이상 지정하세요.")
        if "category" in changes:
            self.require_category(str(changes["category"]))
        # replace(): frozen dataclass 를 바꾸는 대신, 일부 필드만 다른 '새 객체'를 만든다
        return self.transactions.update(tx_id, lambda tx: replace(tx, **changes))  # type: ignore[arg-type]

    def delete_transaction(self, tx_id: str) -> Transaction:
        return self.transactions.delete(tx_id)

    # ---- 요약 / 예산 ------------------------------------------------------
    def monthly_summary(self, month: str, top: int) -> MonthlySummary:
        """한 번의 스트리밍 순회로 수입/지출 합계와 카테고리별 합계를 동시에 계산."""
        income = expense = count = 0
        by_category: defaultdict[str, int] = defaultdict(int)  # 없는 키는 자동으로 0
        for tx in self.transactions.iter_all():
            if tx.month != month:
                continue
            count += 1
            if tx.type == "income":
                income += tx.amount
            else:
                expense += tx.amount
                by_category[tx.category] += tx.amount
        top_items = heapq.nlargest(top, by_category.items(), key=lambda item: item[1])
        return MonthlySummary(month, income, expense, count, top_items, self.budgets.get(month))

    def set_budget(self, month: str, amount: int) -> None:
        self.budgets.set(month, amount)

    # ---- 카테고리 ---------------------------------------------------------
    def add_category(self, name: str) -> bool:
        return self.categories.add(parse_category_name(name))

    def remove_category(self, name: str, replace_with: str | None = None) -> int:
        """카테고리 삭제. 사용 중이면 replace_with 가 있어야 하며, 해당 거래를 대체 카테고리로 옮긴다.

        반환: 대체 카테고리로 옮긴 거래 수
        """
        name = parse_category_name(name)
        if not self.categories.exists(name):
            raise NotFoundError(f"'{name}' 카테고리가 없습니다.", "`category list` 로 목록을 확인하세요.")
        used = sum(1 for tx in self.transactions.iter_all() if tx.category == name)
        used_rules = sum(1 for r in self.recurring.list_rules() if r.category == name)

        moved = 0
        if used or used_rules:
            if replace_with is None:
                raise AppError(
                    f"'{name}' 카테고리를 사용하는 거래 {used}건, 반복 규칙 {used_rules}건이 있어 삭제할 수 없습니다.",
                    "--replace-with <대체카테고리> 옵션으로 옮길 카테고리를 지정하세요.",
                )
            target = parse_category_name(replace_with)
            if target == name:
                raise ValidationError("대체 카테고리는 삭제할 카테고리와 달라야 합니다.")
            self.require_category(target)
            # 순서가 중요: 거래를 먼저 옮기고(원자적) 그다음 카테고리를 지운다.
            # 중간에 실패해도 '카테고리는 남아 있는' 안전한 상태가 된다.
            moved = self.transactions.rewrite(lambda tx: replace(tx, category=target) if tx.category == name else tx)
            self.recurring.replace_category(name, target)
        self.categories.remove(name)
        return moved

    # ---- CSV 가져오기 / 내보내기 -------------------------------------------
    def import_csv(self, src: Path) -> ImportResult:
        """CSV 를 읽어 유효한 행만 등록. 잘못된 행은 건너뛰고 이유를 기록."""
        if not src.is_file():
            raise NotFoundError(f"가져올 파일이 없습니다: {src}", "파일 경로를 확인하세요. 예: import --from ./import.csv")
        result = ImportResult()
        valid: list[Transaction] = []
        categories = set(self.categories.list_names())
        next_no = id_number(self.transactions.next_id())

        # utf-8-sig: 엑셀이 저장한 CSV 맨 앞의 BOM(보이지 않는 문자)을 자동으로 제거
        with src.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            missing = [c for c in CSV_REQUIRED if c not in (reader.fieldnames or [])]
            if missing:
                raise ValidationError(
                    f"CSV 헤더에 필수 컬럼이 없습니다: {', '.join(missing)}",
                    f"첫 줄(헤더)은 다음과 같아야 합니다: {','.join(CSV_COLUMNS)}",
                )
            for row in reader:  # DictReader 도 한 행씩 읽는 이터레이터
                line = reader.line_num
                try:
                    category = parse_category_name(row.get("category") or "")
                    if category not in categories:
                        raise ValidationError(f"등록되지 않은 카테고리 '{category}'")
                    tx = Transaction(
                        id=format_id(TX_PREFIX, next_no),
                        type=parse_type(row.get("type") or ""),
                        date=parse_date(row.get("date") or ""),
                        amount=parse_amount(row.get("amount") or ""),
                        category=category,
                        memo=(row.get("memo") or "").strip(),
                        tags=parse_tags(row.get("tags") or ""),
                    )
                except ValidationError as exc:
                    result.skipped += 1
                    result.errors.append(f"{line}행: {exc.message}")
                    continue
                valid.append(tx)
                next_no += 1

        # 유효한 행은 한 번에 저장 (중간에 파일 오류가 나도 '반쯤 들어간' 상태를 줄임)
        result.imported = self.transactions.append_many(valid)
        return result

    def export_csv(self, out: Path, date_from: str | None, date_to: str | None) -> int:
        """조건에 맞는 거래를 날짜 오름차순으로 CSV 저장. 저장 건수 반환."""
        criteria = SearchCriteria(date_from=date_from, date_to=date_to)
        rows = sorted(self.iter_matching(criteria), key=Transaction.sort_key)
        with atomic_open(out) as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            for tx in rows:
                writer.writerow([tx.date, tx.type, tx.category, tx.amount, tx.memo, ",".join(tx.tags)])
        return len(rows)

    # ---- 백업 (보너스 1) ---------------------------------------------------
    def create_backup(self, label: str = "") -> Path:
        """data/backups/backup-YYYYMMDD-HHMMSS/ 폴더에 모든 저장 파일을 복사."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"backup-{stamp}" + (f"-{label}" if label else "")
        target = self.backup_root / name
        suffix = 1
        while target.exists():  # 1초 안에 여러 번 백업해도 이름이 겹치지 않게
            target = self.backup_root / f"{name}-{suffix}"
            suffix += 1
        target.mkdir(parents=True)
        for filename in self.DATA_FILES:
            source = self.data_dir / filename
            if source.exists():
                shutil.copy2(source, target / filename)  # copy2: 수정 시각 등 메타데이터도 복사
        return target

    def list_backups(self) -> list[Path]:
        if not self.backup_root.exists():
            return []
        return sorted((p for p in self.backup_root.iterdir() if p.is_dir()), reverse=True)

    def restore_backup(self, name: str) -> Path:
        """백업 복원. 복원 직전 현재 상태를 자동 백업해 두므로 '복원을 되돌리기'도 가능."""
        source = self.backup_root / name
        if not source.is_dir():
            raise NotFoundError(f"백업을 찾을 수 없습니다: {name}", "`backup list` 로 백업 이름을 확인하세요.")
        safety = self.create_backup(label="before-restore")
        for filename in self.DATA_FILES:
            backup_file = source / filename
            if backup_file.exists():
                with atomic_open(self.data_dir / filename) as out:
                    out.write(backup_file.read_text(encoding="utf-8"))
        return safety

    # ---- 반복 내역 (보너스 2) ---------------------------------------------
    def add_recurring(
        self, *, name: str, tx_type: str, category: str, amount: int, day: int, memo: str = "", tags: tuple[str, ...] = ()
    ) -> RecurringRule:
        self.require_category(category)
        return self.recurring.add(
            {"name": name, "type": tx_type, "category": category, "amount": amount,
             "day": day, "memo": memo, "tags": list(tags)}
        )

    def apply_recurring(self, month: str) -> ApplyResult:
        """해당 월에 반복 규칙을 적용해 거래 자동 생성. 이미 생성된 규칙은 건너뜀(중복 방지)."""
        result = ApplyResult()
        rules = self.recurring.list_rules()
        if not rules:
            return result
        start, end = month_range(month)
        # 이미 이 달에 만들어진 반복 거래의 키 모으기 (스트리밍)
        existing = {
            tx.recurring_key
            for tx in self.iter_matching(SearchCriteria(date_from=start, date_to=end))
            if tx.recurring_key
        }
        categories = set(self.categories.list_names())
        next_no = id_number(self.transactions.next_id())
        for rule in rules:
            if rule.key_for(month) in existing:
                result.skipped.append(f"{rule.id} {rule.name}: 이미 {month}에 생성됨")
                continue
            if rule.category not in categories:
                result.skipped.append(f"{rule.id} {rule.name}: 카테고리 '{rule.category}' 없음")
                continue
            result.created.append(rule.to_transaction(format_id(TX_PREFIX, next_no), month))
            next_no += 1
        self.transactions.append_many(result.created)
        return result
