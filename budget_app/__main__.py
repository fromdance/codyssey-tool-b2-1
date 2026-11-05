"""`python -m budget_app ...` 으로 실행했을 때 가장 먼저 실행되는 파일.

파이썬은 `-m 패키지명` 으로 실행하면 그 패키지 안의 __main__.py 를 실행한다.
같은 패키지 내 `cli.py`(`.cli`)의 main 문을 불러와 호출하고, 
그 반환값을 기반으로 예외를 발생시켜 프로그램을 종료함.

raise는 예외를 발생시키는 명령어로, 뒤에 예외 객체를 붙일 수 있음.
`SystemExit`는 파이썬 인터프리터가 종료되도록 유도하는 예외로,
`sys.exit()`와 동일하게 선택적 인자를 받음
값이 0일 경우 정상 종료, 이외의 값은 오류 종료
(C의 `exit()`에 전달되는 시스템 종료 상태 값)

(+ `SystemExit`는 Exception이 아닌, BaseException을 상속하기 때문에
Exception을 처리하는 코드에서 잡히지 않음.
https://docs.python.org/ko/3/builtins/exceptions.html#SystemExit)
"""

from .cli import main

raise SystemExit(main())
