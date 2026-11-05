"""CLI 계층: 명령어 해석(argparse) + 대화형 입력(input) + 결과 출력.

흐름
    main(argv)
      └─ build_parser().parse_args()   명령어/옵션 해석. 각 명령에 handler 함수가 연결돼 있음
      └─ run(args)                     @handle_errors : 모든 오류를 친절한 메시지 + 종료 코드로
           ├─ BudgetService 생성, 저장 파일 초기화
           ├─ 로그 설정 (data/app.log)
           └─ args.handler(service, args)   예: cmd_add, cmd_list ...
                                              @log_execution @timed 가 붙어 있음

update 입력 방식은 (안 A) '옵션 기반' 으로 고정:
    update --id TX-000001 --amount 20000 --memo 저녁
"""

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NoReturn, TypeVar

from . import __version__
from .decorators import handle_errors, log_execution, timed
from .errors import AppError, ValidationError
from .formatter import money, print_error, progress_bar, render_table, transactions_table
from .models import (
    RC_PREFIX,
    TX_PREFIX,
    month_range,
    parse_amount,
    parse_category_name,
    parse_date,
    parse_day,
    parse_id,
    parse_month,
    parse_tags,
    parse_type,
    today,
)
from .services import CSV_COLUMNS, BudgetService, SearchCriteria

T = TypeVar("T")
PROG = "python -m budget_app"
WARN_PCT = 80.0  # 예산 사용률이 이 값 이상이면 '주의' 표시


# ===========================================================================
# 1. 대화형 입력 도우미
# ===========================================================================
def ask(label: str, parse: Callable[[str], T], *, default: str | None = None) -> T:
    """올바른 값이 들어올 때까지 반복해서 묻는다(재입력 요구).

    parse 에는 models 의 검증 함수(parse_date 등)를 넘긴다.
    엔터만 치면 default 값을 사용한다.
    """
    while True:
        try:
            raw = input(label)
        except EOFError:  # 입력이 끊긴 경우 (Ctrl+D, 파이프 입력 끝)
            print()
            raise AppError("입력이 중단되었습니다.", "필요한 값을 모두 입력해 주세요.") from None
        if not raw.strip() and default is not None:
            raw = default
        try:
            return parse(raw)
        except ValidationError as exc:
            print_error(exc.message, exc.hint)  # 오류를 알려주고 while 문으로 돌아가 다시 묻는다


def ask_text(label: str) -> str:
    return ask(label, lambda s: s.strip(), default="")


def ask_yes_no(label: str) -> bool:
    return ask(label, lambda s: s.strip().lower() in ("y", "yes", "예", "ㅛ"), default="n")


def ask_category(service: BudgetService, label: str = "카테고리: ") -> str:
    """등록된 카테고리만 받는다. 없는 카테고리면 목록을 보여주고 '등록할지' 물어본다."""
    while True:
        name = ask(label, parse_category_name)
        if service.categories.exists(name):
            return name
        print_error(f"등록되지 않은 카테고리입니다: {name}",
                    f"등록된 카테고리: {', '.join(service.categories.list_names())}")
        if ask_yes_no(f"'{name}' 을(를) 새 카테고리로 등록할까요? (y/N): "):
            service.add_category(name)
            print(f"[저장 완료] category={name}")
            return name


# ===========================================================================
# 2. argparse 설정
# ===========================================================================
class KoreanArgumentParser(argparse.ArgumentParser):
    """옵션 오류도 '[오류] 원인 / [힌트] 해결법' 형식으로 출력하도록 error() 를 재정의."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print_error(f"명령어 사용법이 올바르지 않습니다: {message}", f"'{self.prog} --help' 로 사용법을 확인하세요.")
        sys.exit(2)


def arg_type(parse: Callable[[str], T]) -> Callable[[str], T]:
    """models 의 검증 함수를 argparse 의 type= 에 쓸 수 있게 변환."""

    def convert(raw: str) -> T:
        try:
            return parse(raw)
        except ValidationError as exc:
            raise argparse.ArgumentTypeError(f"{exc.message} {exc.hint or ''}".strip()) from None

    convert.__name__ = parse.__name__.removeprefix("parse_")  # 오류 메시지에 표시될 이름
    return convert


def positive_int(raw: str) -> int:
    if not raw.isdigit() or int(raw) <= 0:
        raise ValidationError(f"1 이상의 정수여야 합니다: {raw!r}", "예: --limit 10")
    return int(raw)


def build_parser() -> argparse.ArgumentParser:
    # 공통 옵션: 어느 위치에 써도 동작하도록 모든 하위 명령에 parents 로 붙인다.
    # default=SUPPRESS → 하위 명령에서 생략하면 상위(main) 파서의 값을 덮어쓰지 않음
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--datadir", default=argparse.SUPPRESS, help="데이터 저장 폴더 (기본: ./data)")
    common.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS, help="실행 로그/시간을 화면에도 출력")

    parser = KoreanArgumentParser(prog=PROG, description="나만의 용돈 기입장 - 콘솔 가계부")
    parser.add_argument("--datadir", default="./data", help="데이터 저장 폴더 (기본: ./data)")
    parser.add_argument("--verbose", action="store_true", default=False, help="실행 로그/시간을 화면에도 출력")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    def add_cmd(subparsers: argparse._SubParsersAction, name: str, help_text: str,
                handler: Callable[[BudgetService, argparse.Namespace], None] | None) -> argparse.ArgumentParser:
        p = subparsers.add_parser(name, help=help_text, description=help_text, parents=[common])
        if handler is not None:
            p.set_defaults(handler=handler)
        return p

    D, M, TY, CAT, AMT = arg_type(parse_date), arg_type(parse_month), arg_type(parse_type), \
        arg_type(parse_category_name), arg_type(parse_amount)
    TXID = arg_type(lambda s: parse_id(s, TX_PREFIX))
    POS = arg_type(positive_int)

    # --- add -------------------------------------------------------------
    add_cmd(sub, "add", "거래 추가 (대화형 입력)", cmd_add)

    # --- list ------------------------------------------------------------
    p = add_cmd(sub, "list", "최신순 거래 목록", cmd_list)
    p.add_argument("--limit", type=POS, default=20, help="표시할 최대 건수 (기본: 20)")

    # --- search ----------------------------------------------------------
    p = add_cmd(sub, "search", "조건 검색 (최신순)", cmd_search)
    p.add_argument("--from", dest="date_from", type=D, metavar="YYYY-MM-DD", help="시작일 (포함)")
    p.add_argument("--to", dest="date_to", type=D, metavar="YYYY-MM-DD", help="종료일 (포함)")
    p.add_argument("--month", type=M, metavar="YYYY-MM", help="특정 월 (--from/--to 대신 사용 가능)")
    p.add_argument("--category", type=CAT)
    p.add_argument("--type", dest="tx_type", type=TY, metavar="income|expense")
    p.add_argument("--q", dest="keyword", metavar="키워드", help="메모에 포함된 단어 (대소문자 무시)")
    p.add_argument("--tag", help="태그 (정확히 일치)")
    p.add_argument("--limit", type=POS, help="최대 건수 (기본: 전체)")

    # --- summary ---------------------------------------------------------
    p = add_cmd(sub, "summary", "월별 요약 (수입/지출/잔액/TOP N/예산)", cmd_summary)
    p.add_argument("--month", type=M, required=True, metavar="YYYY-MM")
    p.add_argument("--top", type=POS, default=3, help="카테고리별 지출 TOP N (기본: 3)")

    # --- budget ----------------------------------------------------------
    p = add_cmd(sub, "budget", "월 예산 설정/조회", None)
    bsub = p.add_subparsers(dest="budget_cmd", metavar="<set|get|list>", required=True)
    bp = add_cmd(bsub, "set", "월 예산 저장 (같은 달이면 덮어쓰기)", cmd_budget_set)
    bp.add_argument("--month", type=M, required=True, metavar="YYYY-MM")
    bp.add_argument("--amount", type=AMT, required=True, metavar="금액")
    bp = add_cmd(bsub, "get", "특정 월 예산 조회", cmd_budget_get)
    bp.add_argument("--month", type=M, required=True, metavar="YYYY-MM")
    add_cmd(bsub, "list", "전체 예산 목록", cmd_budget_list)

    # --- category --------------------------------------------------------
    p = add_cmd(sub, "category", "카테고리 관리", None)
    csub = p.add_subparsers(dest="category_cmd", metavar="<add|list|remove>", required=True)
    cp = add_cmd(csub, "add", "카테고리 추가 (--name 생략 시 대화형)", cmd_category_add)
    cp.add_argument("--name", help="카테고리명")
    add_cmd(csub, "list", "카테고리 목록", cmd_category_list)
    cp = add_cmd(csub, "remove", "카테고리 삭제 (사용 중이면 --replace-with 필요)", cmd_category_remove)
    cp.add_argument("--name", help="삭제할 카테고리명 (생략 시 대화형)")
    cp.add_argument("--replace-with", dest="replace_with", metavar="카테고리", help="사용 중인 거래를 옮길 대체 카테고리")

    # --- update (안 A: 옵션 기반으로 고정) --------------------------------
    p = add_cmd(sub, "update", "거래 수정 (옵션 기반: 지정한 항목만 변경)", cmd_update)
    p.add_argument("--id", dest="tx_id", type=TXID, required=True, metavar="ID")
    p.add_argument("--date", type=D, metavar="YYYY-MM-DD")
    p.add_argument("--type", dest="tx_type", type=TY, metavar="income|expense")
    p.add_argument("--category", type=CAT)
    p.add_argument("--amount", type=AMT, metavar="금액")
    p.add_argument("--memo", help='메모 ("" 로 비우기)')
    p.add_argument("--tags", help='쉼표 구분 태그 ("" 로 비우기)')

    # --- delete ----------------------------------------------------------
    p = add_cmd(sub, "delete", "거래 삭제", cmd_delete)
    p.add_argument("--id", dest="tx_id", type=TXID, required=True, metavar="ID")

    # --- import / export -------------------------------------------------
    p = add_cmd(sub, "import", f"CSV 가져오기 (컬럼: {','.join(CSV_COLUMNS)})", cmd_import)
    p.add_argument("--from", dest="src", type=Path, required=True, metavar="CSV경로")

    p = add_cmd(sub, "export", "CSV 내보내기 (--month 또는 --from/--to 필수)", cmd_export)
    p.add_argument("--out", type=Path, required=True, metavar="CSV경로")
    p.add_argument("--month", type=M, metavar="YYYY-MM")
    p.add_argument("--from", dest="date_from", type=D, metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", type=D, metavar="YYYY-MM-DD")

    # --- backup (보너스 1) -----------------------------------------------
    p = add_cmd(sub, "backup", "백업 생성/목록/복원 (하위 명령 생략 시 생성)", cmd_backup_create)
    ksub = p.add_subparsers(dest="backup_cmd", metavar="<create|list|restore>")
    add_cmd(ksub, "create", "타임스탬프 백업 생성", cmd_backup_create)
    add_cmd(ksub, "list", "백업 목록", cmd_backup_list)
    kp = add_cmd(ksub, "restore", "백업 복원 (복원 전 현재 상태 자동 백업)", cmd_backup_restore)
    kp.add_argument("--name", required=True, help="복원할 백업 이름 (backup list 참고)")

    # --- recurring (보너스 2) --------------------------------------------
    p = add_cmd(sub, "recurring", "반복 내역(월급/월세 등) 관리", None)
    rsub = p.add_subparsers(dest="recurring_cmd", metavar="<add|list|remove|apply>", required=True)
    add_cmd(rsub, "add", "반복 규칙 추가 (대화형)", cmd_recurring_add)
    add_cmd(rsub, "list", "반복 규칙 목록", cmd_recurring_list)
    rp = add_cmd(rsub, "remove", "반복 규칙 삭제", cmd_recurring_remove)
    rp.add_argument("--id", dest="rule_id", type=arg_type(lambda s: parse_id(s, RC_PREFIX)), required=True, metavar="ID")
    rp = add_cmd(rsub, "apply", "특정 월에 반복 거래 자동 생성 (중복 생성 방지)", cmd_recurring_apply)
    rp.add_argument("--month", type=M, required=True, metavar="YYYY-MM")

    return parser


# ===========================================================================
# 3. 명령 핸들러 (각 명령 = 함수 1개)
#    공통 데코레이터: @log_execution(로그) + @timed(시간 측정)
# ===========================================================================
@log_execution
@timed
def cmd_add(service: BudgetService, args: argparse.Namespace) -> None:
    date = ask(f"날짜(YYYY-MM-DD, 엔터=오늘 {today()}): ", parse_date, default=today())
    tx_type = ask("타입(income/expense): ", parse_type)
    category = ask_category(service)
    amount = ask("금액(양수): ", parse_amount)
    memo = ask_text("메모(선택): ")
    tags = ask("태그(쉼표로 구분, 없으면 엔터): ", parse_tags, default="")
    tx = service.add_transaction(tx_type=tx_type, date=date, category=category, amount=amount, memo=memo, tags=tags)
    print(f"[저장 완료] id={tx.id}")


@log_execution
@timed
def cmd_list(service: BudgetService, args: argparse.Namespace) -> None:
    print(transactions_table(service.latest(args.limit)))


@log_execution
@timed
def cmd_search(service: BudgetService, args: argparse.Namespace) -> None:
    date_from, date_to = resolve_period(args.month, args.date_from, args.date_to, required=False)
    criteria = SearchCriteria(
        date_from=date_from, date_to=date_to, category=args.category,
        tx_type=args.tx_type, keyword=args.keyword, tag=args.tag,
    )
    results = service.search(criteria, args.limit)
    print(transactions_table(results))
    print(f"\n총 {len(results)}건")


@log_execution
@timed
def cmd_summary(service: BudgetService, args: argparse.Namespace) -> None:
    s = service.monthly_summary(args.month, args.top)
    print(f"=== {s.month} 월별 요약 ===")
    if s.count == 0:
        print("데이터 없음 (해당 월에 등록된 거래가 없습니다)")
    else:
        rows = [["총 수입", money(s.income)], ["총 지출", money(s.expense)], ["잔액", money(s.balance)]]
        print(render_table(["항목", "금액"], rows, ["left", "right"]))

    if s.budget is not None and s.usage_pct is not None:
        print(f"\n예산: {money(s.budget)} (사용률 {s.usage_pct:.1f}%) {progress_bar(s.usage_pct)}")
        if s.over_budget:
            print(f"[경고] 예산을 {money(s.over_budget)} 초과했습니다!")
        elif s.usage_pct >= WARN_PCT:
            print(f"[주의] 예산의 {WARN_PCT:.0f}% 이상을 사용했습니다. 남은 예산: {money(s.budget - s.expense)}")
        else:
            print(f"남은 예산: {money(s.budget - s.expense)}")
    else:
        print(f"\n(예산 미설정 — `budget set --month {s.month} --amount 금액` 으로 설정)")

    if s.count:
        print(f"\n지출 TOP {args.top}")
        if not s.top_categories:
            print("  (지출 없음)")
        else:
            rows = [
                [f"{rank})", category, money(total), f"{total / s.expense * 100:.1f}%"]
                for rank, (category, total) in enumerate(s.top_categories, start=1)
            ]
            print(render_table(["순위", "카테고리", "지출", "비중"], rows, ["left", "left", "right", "right"]))


@log_execution
@timed
def cmd_budget_set(service: BudgetService, args: argparse.Namespace) -> None:
    service.set_budget(args.month, args.amount)
    print(f"[저장 완료] {args.month} 예산 {money(args.amount)}")


@log_execution
@timed
def cmd_budget_get(service: BudgetService, args: argparse.Namespace) -> None:
    amount = service.budgets.get(args.month)
    print(f"{args.month} 예산: {money(amount)}" if amount is not None else f"{args.month} 예산이 설정되지 않았습니다.")


@log_execution
@timed
def cmd_budget_list(service: BudgetService, args: argparse.Namespace) -> None:
    budgets = service.budgets.all()
    if not budgets:
        print("(설정된 예산이 없습니다)")
        return
    print(render_table(["월", "예산"], [[m, money(a)] for m, a in budgets.items()], ["left", "right"]))


@log_execution
@timed
def cmd_category_add(service: BudgetService, args: argparse.Namespace) -> None:
    name = parse_category_name(args.name) if args.name else ask("카테고리명: ", parse_category_name)
    if service.add_category(name):
        print(f"[저장 완료] category={name}")
    else:
        print(f"[안내] 이미 등록된 카테고리입니다: {name}")


@log_execution
@timed
def cmd_category_list(service: BudgetService, args: argparse.Namespace) -> None:
    for name in service.categories.list_names():
        print(f"- {name}")


@log_execution
@timed
def cmd_category_remove(service: BudgetService, args: argparse.Namespace) -> None:
    name = args.name or ask("삭제할 카테고리명: ", parse_category_name)
    moved = service.remove_category(name, args.replace_with)
    if moved:
        print(f"[이동 완료] 거래 {moved}건을 '{parse_category_name(args.replace_with)}' 로 옮겼습니다.")
    print(f"[삭제 완료] category={parse_category_name(name)}")


@log_execution
@timed
def cmd_update(service: BudgetService, args: argparse.Namespace) -> None:
    # None 이 아닌(=사용자가 지정한) 옵션만 변경 목록에 담는다
    changes: dict[str, object] = {}
    if args.date is not None:
        changes["date"] = args.date
    if args.tx_type is not None:
        changes["type"] = args.tx_type
    if args.category is not None:
        changes["category"] = args.category
    if args.amount is not None:
        changes["amount"] = args.amount
    if args.memo is not None:
        changes["memo"] = args.memo.strip()
    if args.tags is not None:
        changes["tags"] = parse_tags(args.tags)
    tx = service.update_transaction(args.tx_id, changes)
    print(f"[수정 완료] id={tx.id} (변경: {', '.join(changes)})")
    print(transactions_table([tx]))


@log_execution
@timed
def cmd_delete(service: BudgetService, args: argparse.Namespace) -> None:
    tx = service.delete_transaction(args.tx_id)
    print(f"[삭제 완료] id={tx.id} ({tx.date} {tx.category} {money(tx.amount)})")


@log_execution
@timed
def cmd_import(service: BudgetService, args: argparse.Namespace) -> None:
    result = service.import_csv(args.src)
    for message in result.errors[:20]:
        print(f"  [건너뜀] {message}")
    if len(result.errors) > 20:
        print(f"  ... 외 {len(result.errors) - 20}건")
    print(f"[완료] imported={result.imported}, skipped={result.skipped}")


@log_execution
@timed
def cmd_export(service: BudgetService, args: argparse.Namespace) -> None:
    date_from, date_to = resolve_period(args.month, args.date_from, args.date_to, required=True)
    count = service.export_csv(args.out, date_from, date_to)
    print(f"[완료] {args.out} ({count} records)")


@log_execution
@timed
def cmd_backup_create(service: BudgetService, args: argparse.Namespace) -> None:
    path = service.create_backup()
    print(f"[백업 완료] {path}")


@log_execution
@timed
def cmd_backup_list(service: BudgetService, args: argparse.Namespace) -> None:
    backups = service.list_backups()
    if not backups:
        print("(백업이 없습니다 — `backup` 으로 생성)")
    for path in backups:
        print(f"- {path.name}")


@log_execution
@timed
def cmd_backup_restore(service: BudgetService, args: argparse.Namespace) -> None:
    safety = service.restore_backup(args.name)
    print(f"[복원 완료] {args.name}")
    print(f"[안내] 복원 직전 상태는 {safety.name} 에 백업해 두었습니다.")


@log_execution
@timed
def cmd_recurring_add(service: BudgetService, args: argparse.Namespace) -> None:
    name = ask("규칙 이름(예: 월급): ", lambda s: s.strip() or _raise_empty())
    tx_type = ask("타입(income/expense): ", parse_type)
    category = ask_category(service)
    amount = ask("금액(양수): ", parse_amount)
    day = ask("매월 며칠(1~31): ", parse_day)
    memo = ask_text("메모(선택, 엔터=규칙 이름): ")
    tags = ask("태그(쉼표로 구분, 없으면 엔터): ", parse_tags, default="")
    rule = service.add_recurring(name=name, tx_type=tx_type, category=category, amount=amount, day=day, memo=memo, tags=tags)
    print(f"[저장 완료] id={rule.id} (매월 {rule.day}일 {rule.category} {money(rule.amount)})")


@log_execution
@timed
def cmd_recurring_list(service: BudgetService, args: argparse.Namespace) -> None:
    rules = service.recurring.list_rules()
    if not rules:
        print("(등록된 반복 규칙이 없습니다 — `recurring add` 로 추가)")
        return
    rows = [[r.id, r.name, r.type, r.category, f"{r.amount:,}", f"매월 {r.day}일"] for r in rules]
    print(render_table(["ID", "이름", "타입", "카테고리", "금액", "주기"], rows,
                       ["left", "left", "left", "left", "right", "left"]))


@log_execution
@timed
def cmd_recurring_remove(service: BudgetService, args: argparse.Namespace) -> None:
    rule = service.recurring.remove(args.rule_id)
    print(f"[삭제 완료] id={rule.id} ({rule.name})")


@log_execution
@timed
def cmd_recurring_apply(service: BudgetService, args: argparse.Namespace) -> None:
    result = service.apply_recurring(args.month)
    for tx in result.created:
        print(f"  [생성] {tx.id} {tx.date} {tx.category} {money(tx.amount)} ({tx.memo})")
    for message in result.skipped:
        print(f"  [건너뜀] {message}")
    print(f"[완료] created={len(result.created)}, skipped={len(result.skipped)}")


# ===========================================================================
# 4. 기타 도우미
# ===========================================================================
def _raise_empty() -> str:
    raise ValidationError("값이 비어 있습니다.", "한 글자 이상 입력하세요.")


def resolve_period(month: str | None, date_from: str | None, date_to: str | None,
                   *, required: bool) -> tuple[str | None, str | None]:
    """--month 와 --from/--to 를 (시작일, 종료일) 로 통일."""
    if month and (date_from or date_to):
        raise ValidationError("--month 와 --from/--to 는 함께 쓸 수 없습니다.", "둘 중 하나만 지정하세요.")
    if month:
        return month_range(month)
    if required and not (date_from or date_to):
        raise ValidationError("기간 조건이 필요합니다.", "--month YYYY-MM 또는 --from YYYY-MM-DD --to YYYY-MM-DD 를 지정하세요.")
    if date_from and date_to and date_from > date_to:
        raise ValidationError(f"시작일({date_from})이 종료일({date_to})보다 늦습니다.", "--from 과 --to 를 바꿔 보세요.")
    return date_from, date_to


def setup_logging(data_dir: Path, verbose: bool) -> None:
    """로그는 data/app.log 파일에 쌓는다. --verbose 면 화면(stderr)에도 출력."""
    logger = logging.getLogger("budget_app")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):  # main() 이 여러 번 호출돼도 중복 기록되지 않게
        if not isinstance(handler, logging.NullHandler):
            logger.removeHandler(handler)
            handler.close()
    file_handler = logging.FileHandler(data_dir / "app.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
    if verbose:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(logging.Formatter("[로그] %(message)s"))
        logger.addHandler(stream)


@handle_errors
def run(args: argparse.Namespace) -> int:
    service = BudgetService(Path(args.datadir))
    for notice in service.initialize():
        print(f"[안내] {notice}", file=sys.stderr)
    setup_logging(service.data_dir, args.verbose)
    args.handler(service, args)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """프로그램 진입점. 종료 코드를 반환한다 (0=정상)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)
