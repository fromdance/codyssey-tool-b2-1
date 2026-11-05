"""출력 포맷터: '화면에 어떻게 보일지'만 책임진다. (보너스 3: 외부 라이브러리 없이 테이블 정렬)

한글 정렬 문제
    파이썬의 len("점심") 은 2지만, 터미널에서 한글은 한 글자가 영문 2칸 폭을 차지한다.
    그래서 str.ljust() 만 쓰면 한글이 섞인 열이 삐뚤어진다.
    unicodedata.east_asian_width() 로 '넓은 문자(W/F)'는 2칸으로 계산해 맞춘다.
"""

import sys
import unicodedata
from collections.abc import Sequence

from .models import Transaction

Align = str  # "left" | "right"


def display_width(text: str) -> int:
    """터미널에서 차지하는 실제 칸 수."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def truncate(text: str, max_width: int) -> str:
    """max_width 칸을 넘으면 잘라내고 '…' 를 붙인다."""
    if display_width(text) <= max_width:
        return text
    out, width = "", 0
    for ch in text:
        w = display_width(ch)
        if width + w > max_width - 1:
            break
        out += ch
        width += w
    return out + "…"


def pad(text: str, width: int, align: Align = "left") -> str:
    gap = max(0, width - display_width(text))
    return " " * gap + text if align == "right" else text + " " * gap


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]], aligns: Sequence[Align]) -> str:
    """헤더 + 구분선 + 행들을 열 너비에 맞춰 정렬한 문자열로 만든다."""
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(cell))

    def fmt(cells: Sequence[str]) -> str:
        return " | ".join(pad(c, widths[i], aligns[i]) for i, c in enumerate(cells)).rstrip()

    lines = [fmt(headers), "-+-".join("-" * w for w in widths)]
    lines += [fmt(row) for row in rows]
    return "\n".join(lines)


def money(amount: int) -> str:
    """15000 → '15,000원'"""
    return f"{amount:,}원"


def transactions_table(transactions: Sequence[Transaction]) -> str:
    if not transactions:
        return "(조건에 맞는 거래 내역이 없습니다)"
    headers = ["ID", "날짜", "타입", "카테고리", "금액", "메모", "태그"]
    aligns = ["left", "left", "left", "left", "right", "left", "left"]
    rows = [
        [
            tx.id,
            tx.date,
            tx.type,
            tx.category,
            f"{tx.amount:,}",
            truncate(tx.memo, 24),
            truncate(",".join(tx.tags), 20),
        ]
        for tx in transactions
    ]
    return render_table(headers, rows, aligns)


def progress_bar(pct: float, width: int = 20) -> str:
    """43.0 → '[########------------]'  (100% 를 넘으면 가득 찬 막대)"""
    filled = min(width, round(width * pct / 100))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def print_error(message: str, hint: str | None = None) -> None:
    """오류는 표준 에러(stderr)로 출력. 정상 출력(stdout)과 섞이지 않게."""
    print(f"[오류] {message}", file=sys.stderr)
    if hint:
        print(f"[힌트] {hint}", file=sys.stderr)
