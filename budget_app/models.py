"""데이터 모델(dataclass)과 입력 검증 함수.

이 모듈은 '데이터가 어떤 모양이어야 하는가'만 책임진다.
파일 저장이나 화면 출력은 전혀 모른다 → 다른 계층에서 마음껏 재사용 가능.

[검증 함수 규칙]
    parse_xxx(raw: str) -> 정리된 값
    - 올바르면 정리(normalize)된 값을 돌려준다. 예: " 2024-1-5 " → "2024-01-05"
    - 틀리면 ValidationError(원인, 힌트)를 발생시킨다.
    대화형 입력(cli), 옵션 인자(argparse), CSV 가져오기(services)가
    모두 같은 함수를 쓰기 때문에 검증 규칙이 한 곳에서 관리된다.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .errors import ValidationError

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
TX_TYPES: tuple[str, ...] = ("income", "expense")
TYPE_ALIASES: dict[str, str] = {"수입": "income", "지출": "expense", "in": "income", "out": "expense"}

TX_PREFIX = "TX"   # 거래 id 접두어  → TX-000001
RC_PREFIX = "RC"   # 반복 규칙 id 접두어 → RC-000001

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_ID_RE = re.compile(r"^([A-Z]+)-(\d+)$")


# ---------------------------------------------------------------------------
# id 도우미
# ---------------------------------------------------------------------------
def format_id(prefix: str, number: int) -> str:
    """(TX, 12) → 'TX-000012'. 6자리 0 채우기."""
    return f"{prefix}-{number:06d}"


def id_number(identifier: str) -> int:
    """'TX-000012' → 12. 형식이 다르면 0."""
    match = _ID_RE.match(identifier)
    return int(match.group(2)) if match else 0


def parse_id(raw: str, prefix: str = TX_PREFIX) -> str:
    """사용자가 입력한 id를 표준 형식으로 정리한다.

    'tx-000012', 'TX-12', '12' 모두 → 'TX-000012'
    """
    value = raw.strip().upper()
    if value.isdigit():
        return format_id(prefix, int(value))
    match = _ID_RE.match(value)
    if not match or match.group(1) != prefix:
        raise ValidationError(f"id 형식이 올바르지 않습니다: {raw!r}", f"예: {format_id(prefix, 12)} 또는 12")
    return format_id(prefix, int(match.group(2)))


# ---------------------------------------------------------------------------
# 입력 검증 함수
# ---------------------------------------------------------------------------
def parse_date(raw: str) -> str:
    """'YYYY-MM-DD' 형식 검증. 존재하지 않는 날짜(2024-13-40)도 걸러낸다."""
    value = raw.strip()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        # `from None` : 내부 ValueError 의 스택트레이스 연결을 끊어 메시지를 깔끔하게 유지
        raise ValidationError("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).", "예: 2024-01-15") from None
    return parsed.isoformat()  # 항상 '2024-01-05' 처럼 0이 채워진 형태로 통일


def parse_month(raw: str) -> str:
    """'YYYY-MM' 형식 검증."""
    value = raw.strip()
    if not _MONTH_RE.match(value) or not 1 <= int(value[5:]) <= 12:
        raise ValidationError("월 형식이 올바르지 않습니다 (YYYY-MM).", "예: 2024-01")
    return value


def parse_amount(raw: str | int) -> int:
    """금액 검증: 양의 정수만 허용. '15,000' 처럼 쉼표가 있어도 허용."""
    text = str(raw).strip().replace(",", "").removesuffix("원")
    if not text.isdigit():
        raise ValidationError(f"금액은 양의 정수여야 합니다: {raw!r}", "예: 15000 (소수점·음수·문자 불가)")
    amount = int(text)
    if amount <= 0:
        raise ValidationError("금액은 0보다 커야 합니다.", "예: 15000")
    return amount


def parse_type(raw: str) -> str:
    """거래 타입 검증: income / expense (한글 '수입'/'지출'도 허용)."""
    value = raw.strip().lower()
    value = TYPE_ALIASES.get(value, value)
    if value not in TX_TYPES:
        raise ValidationError(f"허용되지 않은 타입입니다: {raw!r}", "income(수입) 또는 expense(지출) 중 하나를 입력하세요.")
    return value


def parse_tags(raw: str) -> tuple[str, ...]:
    """'meal, lunch,,meal' → ('meal', 'lunch')  (공백 제거, 빈 값/중복 제거, 순서 유지)."""
    tags = [t.strip() for t in raw.split(",") if t.strip()]
    return tuple(dict.fromkeys(tags))  # dict 키는 중복이 없고 순서를 유지한다는 성질 활용


def parse_category_name(raw: str) -> str:
    """카테고리 이름 검증: 비어 있지 않고, 쉼표 없음, 20자 이하."""
    value = raw.strip().lower()
    if not value:
        raise ValidationError("카테고리 이름이 비어 있습니다.", "예: food")
    if "," in value or len(value) > 20:
        raise ValidationError("카테고리 이름은 쉼표 없이 20자 이하여야 합니다.", "예: food, transport")
    return value


def parse_day(raw: str | int) -> int:
    """반복 내역의 '매월 며칠' 검증: 1~31."""
    text = str(raw).strip()
    if not text.isdigit() or not 1 <= int(text) <= 31:
        raise ValidationError("일(day)은 1~31 사이 정수여야 합니다.", "예: 25 (31을 넣으면 짧은 달은 말일로 처리)")
    return int(text)


def month_range(month: str) -> tuple[str, str]:
    """'2024-02' → ('2024-02-01', '2024-02-29'). 윤년도 calendar 모듈이 계산해 준다."""
    year, mon = int(month[:4]), int(month[5:])
    last_day = calendar.monthrange(year, mon)[1]
    return f"{month}-01", f"{month}-{last_day:02d}"


def today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Transaction:
    """거래 1건.

    @dataclass 가 __init__, __repr__, __eq__ 를 자동으로 만들어 준다.
    frozen=True → 만든 뒤 값을 바꿀 수 없음(불변). 수정은 dataclasses.replace()로
    '새 객체'를 만들어서 한다 → 실수로 원본이 바뀌는 버그를 막는다.
    """

    id: str
    type: str                     # 'income' | 'expense'
    date: str                     # 'YYYY-MM-DD'
    amount: int                   # 양의 정수
    category: str
    memo: str = ""
    tags: tuple[str, ...] = ()
    recurring_key: str | None = None  # 반복 내역으로 자동 생성된 경우 'RC-000001@2024-01'

    @property
    def month(self) -> str:
        """'2024-01-15' → '2024-01'"""
        return self.date[:7]

    def sort_key(self) -> tuple[str, int]:
        """최신순 정렬 기준: (날짜, id 번호). 같은 날짜면 나중에 등록한 것이 더 최신."""
        return (self.date, id_number(self.id))

    def to_dict(self) -> dict[str, Any]:
        """파일 저장용 dict 로 변환 (tuple → list: JSON 에는 tuple 이 없으므로)."""
        data: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "date": self.date,
            "amount": self.amount,
            "category": self.category,
            "memo": self.memo,
            "tags": list(self.tags),
        }
        if self.recurring_key:
            data["recurring_key"] = self.recurring_key
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        """파일에서 읽은 dict → Transaction. 읽을 때도 검증해서 손상된 데이터를 잡아낸다."""
        try:
            return cls(
                id=str(data["id"]),
                type=parse_type(str(data["type"])),
                date=parse_date(str(data["date"])),
                amount=parse_amount(data["amount"]),
                category=str(data["category"]),
                memo=str(data.get("memo") or ""),
                tags=tuple(str(t) for t in data.get("tags") or ()),
                recurring_key=data.get("recurring_key"),
            )
        except KeyError as exc:
            raise ValidationError(f"필수 필드가 없습니다: {exc.args[0]}") from None


@dataclass(frozen=True)
class RecurringRule:
    """반복 내역 규칙 (보너스 과제 2). 예: 매월 25일 salary 3,000,000원 수입."""

    id: str
    name: str
    type: str
    category: str
    amount: int
    day: int          # 매월 며칠 (1~31)
    memo: str = ""
    tags: tuple[str, ...] = ()

    def date_in(self, month: str) -> str:
        """해당 월의 실제 발생일. day=31 인데 2월이면 → 2월 말일."""
        _, last = month_range(month)
        last_day = int(last[-2:])
        return f"{month}-{min(self.day, last_day):02d}"

    def key_for(self, month: str) -> str:
        """같은 달에 두 번 생성되는 것을 막기 위한 고유 키."""
        return f"{self.id}@{month}"

    def to_transaction(self, tx_id: str, month: str) -> Transaction:
        return Transaction(
            id=tx_id,
            type=self.type,
            date=self.date_in(month),
            amount=self.amount,
            category=self.category,
            memo=self.memo or self.name,
            tags=self.tags,
            recurring_key=self.key_for(month),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "type": self.type, "category": self.category,
            "amount": self.amount, "day": self.day, "memo": self.memo, "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecurringRule":
        try:
            return cls(
                id=str(data["id"]),
                name=str(data["name"]),
                type=parse_type(str(data["type"])),
                category=str(data["category"]),
                amount=parse_amount(data["amount"]),
                day=parse_day(data["day"]),
                memo=str(data.get("memo") or ""),
                tags=tuple(str(t) for t in data.get("tags") or ()),
            )
        except KeyError as exc:
            raise ValidationError(f"필수 필드가 없습니다: {exc.args[0]}") from None
