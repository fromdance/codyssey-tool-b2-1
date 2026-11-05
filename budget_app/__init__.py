"""나만의 용돈 기입장 (콘솔 가계부) 패키지.

패키지 구조 (계층별 책임)
    models.py      : 데이터 구조(Transaction, RecurringRule)와 입력 검증 함수
    errors.py      : 프로그램 전용 예외 클래스 (오류 메시지 + 해결 힌트)
    storage.py     : 파일 입출력 (JSONL 읽기/쓰기, 원자적 저장)
    services.py    : 비즈니스 로직 (추가/검색/요약/예산/가져오기/백업/반복 내역)
    decorators.py  : 공통 관심사 (예외 처리, 실행 로그, 실행 시간 측정)
    formatter.py   : 콘솔 출력 형식 (테이블 정렬, 금액 표시)
    cli.py         : 명령어 해석(argparse)과 대화형 입력
    __main__.py    : `python -m budget_app` 실행 진입점
"""

__version__ = "1.0.0"
