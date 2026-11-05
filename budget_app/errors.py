"""프로그램 전용 예외(Exception) 클래스 모음.

왜 따로 만드나?
    파이썬 기본 예외(ValueError 등)를 그대로 쓰면 '사용자에게 보여줄 오류'와
    '프로그래머 실수로 생긴 버그'를 구분하기 어렵다.
    AppError 계열은 "사용자에게 원인 + 해결 힌트를 보여주면 되는 오류"라는 약속이다.
    decorators.handle_errors 가 이 예외를 잡아 스택트레이스 대신 친절한 메시지로 출력한다.
"""


class AppError(Exception):
    """사용자에게 보여줄 오류의 공통 부모 클래스.

    Attributes:
        message:   무엇이 잘못됐는지 (원인)
        hint:      어떻게 고치면 되는지 (해결 힌트, 없을 수도 있음)
        exit_code: 프로그램 종료 코드 (0이 아닌 값)
    """

    exit_code: int = 1

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class ValidationError(AppError):
    """사용자 입력 값이 형식/규칙에 맞지 않을 때 (날짜 형식, 음수 금액 등)."""


class NotFoundError(AppError):
    """요청한 데이터(id, 카테고리, 백업 등)가 존재하지 않을 때."""

    exit_code = 3


class StorageError(AppError):
    """저장 파일을 읽거나 쓰는 데 실패했을 때 (파일 손상, 권한 문제 등)."""

    exit_code = 4
