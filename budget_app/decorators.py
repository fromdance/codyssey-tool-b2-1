"""데코레이터: 여러 명령에 공통으로 필요한 기능(공통 관심사)을 한 곳에 모은다.

데코레이터란?
    '함수를 받아서, 기능을 덧붙인 새 함수를 돌려주는 함수'.

        @timed
        def cmd_list(...): ...

    는 사실 아래와 똑같다:

        def cmd_list(...): ...
        cmd_list = timed(cmd_list)

    덕분에 cmd_list 본문에는 '목록 출력' 코드만 남고,
    시간 측정/로그/예외 처리 코드는 여기 한 곳에서만 관리된다.

여기 있는 3가지
    handle_errors  : 예외를 잡아 스택트레이스 대신 "[오류] 원인 / [힌트] 해결법" 출력 + 종료 코드 반환
    log_execution  : 명령 시작/완료/실패를 로그 파일(data/app.log)에 기록
    timed          : 실행 시간을 측정해 로그에 기록 (--verbose 면 화면에도 표시)
"""

import functools
import logging
import sys
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from .errors import AppError
from .formatter import print_error

# ParamSpec / TypeVar : "감싼 함수와 똑같은 인자·반환 타입을 가진다"는 것을 타입 힌트로 표현.
# 덕분에 데코레이터를 붙여도 편집기(IDE)가 원래 함수의 인자 정보를 그대로 보여준다.
P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger("budget_app")
logger.addHandler(logging.NullHandler())  # 로그 설정 전이라도 경고 메시지가 화면에 새지 않게


def log_execution(func: Callable[P, R]) -> Callable[P, R]:
    """실행 로그 데코레이터."""

    @functools.wraps(func)  # 원래 함수 이름/설명(__name__, __doc__)을 유지
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.info("실행 시작: %s", func.__name__)
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            logger.warning("실행 실패: %s (%s: %s)", func.__name__, type(exc).__name__, exc)
            raise  # 잡은 예외를 그대로 다시 던져서 handle_errors 가 처리하게 함
        logger.info("실행 완료: %s", func.__name__)
        return result

    return wrapper


def timed(func: Callable[P, R]) -> Callable[P, R]:
    """실행 시간 측정 데코레이터."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()  # 짧은 시간 측정에 적합한 고정밀 타이머
        try:
            return func(*args, **kwargs)
        finally:  # 성공하든 예외가 나든 반드시 실행
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info("실행 시간: %s %.2fms", func.__name__, elapsed_ms)

    return wrapper


def handle_errors(func: Callable[P, int]) -> Callable[P, int]:
    """예외 처리 데코레이터. 감싼 함수는 종료 코드(int)를 반환해야 한다.

    종료 코드 규칙
        0   : 정상
        1   : 일반 오류 (AppError, 예기치 못한 오류)
        3   : 데이터 없음 (NotFoundError)
        4   : 저장소 오류 (StorageError)
        130 : 사용자가 Ctrl+C 로 중단
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> int:
        try:
            return func(*args, **kwargs)
        except AppError as exc:
            print_error(exc.message, exc.hint)
            return exc.exit_code
        except KeyboardInterrupt:
            print("\n[중단] 사용자가 작업을 취소했습니다.", file=sys.stderr)
            return 130
        except OSError as exc:  # 권한 없음, 디스크 가득 참 등
            print_error(f"파일 처리 중 문제가 발생했습니다: {exc.strerror} ({exc.filename})", "경로와 쓰기 권한을 확인하세요.")
            return 1
        except Exception as exc:  # 예상 못 한 버그: 화면엔 요약만, 상세 스택트레이스는 로그 파일에만
            logger.exception("예기치 못한 오류")
            print_error(f"예기치 못한 오류가 발생했습니다: {type(exc).__name__}: {exc}",
                        "자세한 내용은 데이터 폴더의 app.log 를 확인하세요.")
            return 1

    return wrapper
