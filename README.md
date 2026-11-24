# codyssey-tool-b2-1
Codyssey All-in-One &lt;AI 도구 학습 - B2-1> 나만의 용돈 기입장 프로그램 만들기

## 나만의 용돈 기입장 (budget_app)

- 파일 기반 콘솔 가계부로, 표준 라이브러리만 사용하며 `Python 3.10` 이상에서 동작합니다.
(제너레이터 스트리밍 / 데코레이터 / 타입 힌트 / 원자적 저장 / 모듈 분리 적용)

## 기능 요구 사항

### 1. 실행 및 입력 방식

- [x] `python -m budget_app <command> [options]` 형태로 실행됨
  > 이는 `budget_app` 패키지의 `__main__.py`를 실행하라는 뜻
- [x] 모든 명령어는 `--help` 옵션으로 사용 방법 출력됨
- [x] 입력 방식은 대화형이되, `search`, `list`, `summary`, `export`, `import`, `delete`는 옵션을 허용한다.
- [x] `update`는 옵션 방식/대화형 중 하나를 선택해야 함 -> 옵션 방식으로 구현
- [x] 옵션 표기는 `--`(ex. `--help`)로 통일한다.

### 2. 데이터 모델

- [x] 거래 내역(Transaction)은 최소 아래 필드를 포함한다.
  - `id`, `type`, `date`, `amount`, `category`, `memo`, `tags`
  > models.py 의 `Transaction`
- [x] 데이터 모델을 `dataclass`에 준하는 구조로 정의한다.
  > `@dataclass`란, 사용자 정의 클래스에 `__init__`, `__repr__`와 같은 `보일러플레이트 메서드 자동 생성`, `프로퍼티 선언 가독성 향상 및 디폴트 값 세팅을 가능`하게해주는 데코레이터 <br/>
  > `models.py`의 `Transaction`, `RecurringRule`이 데이터 모델
- [x] 최소 2개 이상의 클래스를 사용한다.
  > `models.py`: Transaction <br/>
  > `services.py`: SearchCriteria, MonthlySummary, ImportResult, ApplyResult, BudgetService <br />
  > `storage.py`: JsonlTable, TransactionRepository, CategoryStore, BudgetStore, RecurringStore
- [x] 입력 검증
  > `models.py`의 `parse_*` 함수들이 입력을 검증함

## 3. 저장 정책
- [x] 저장 포맷은 JSONL 또는 CSV 중 1개를 선택한다.
  > 내부적으로 사용하는 데이터들은 JSONL을 사용함 <br/>
  > `JSONL`은 `태그`처럼 리스트로 관리해야 하는 값을 그대로 배열로 사용할 수 있고, *CSV와 달리* 숫자/문자 구분이 명확하며, 필드 추가시 예전 데이터가 깨지는 일도 없다는 장점이 있음 
  > 외부에 가져오기/내보내기 할 때는 CSV 포맷을 사용함
- [x] 저장 파일은 3개 이상(필수) 로 분리해 영구 저장한다.
  > (`data/transactions.jsonl`, `categories.jsonl`, `budgets.jsonl`, `recurring.jsonl`)
- [x] 기본 저장 폴더는 ./data를 권장하며, 옵션으로 변경 가능해야 한다(예: -data-dir).
  > 가계부 서비스의 주요 비즈니스 로직을 처리하는 `BudgetService` 생성 시, CLI에서 인자로 받은 `data-dir`을 저장 폴더로 사용함
  ```python
  // cli.py > run()
  service = BudgetService(Path(args.datadir))
  ```
- [x] 초기 실행시, 파일이 없으면 자동 생성하거나, “초기화 안내 메시지”를 출력해야 한다.
    > `service.py`의 `BudgetService.initialize`에서 기본 카테고리 `store`별로 `ensure_file`(해당 `store` 경로에 폴더 및 파일가 없으면 생성)을 호출해 `자동 생성`한다.
- 초기 실행시, 카테고리 파일이 비어있으면 아래 중 하나를 택해 동작을 명확히 한다.
  - [x] (안 A) 기본 카테고리 자동 생성(예: food, transport, rent, etc)
    > `BudgetService.initialize`에서 초기화 시, `DEFAULT_CATEGORIES`(`"food", "transport", "rent", "shopping", "salary", "allowance", "etc"`)으로 초기화
## 4. `add`(거래 추가)
- [x] 대화형으로 필드를 입력받아 거래를 저장한다.
    > `add` 호출시 `cli.py`의 `cmd_add`가 호출되며, 이는 `input()` 기반의 입력 처리 함수 `ask`를 반복적으로 호출하는 형태다.
- [x] `category`는 등록된 목록에 존재해야 한다.(없을시 안내 및 재입력/등록 유도)
    > `cli.py`의 `ask_category`를 이용해 카테고리를 입력받는데, 이는 `service.categories.exists(name)`를 통해 존재하는 카테고리인지 검사하며, 존재하지 않을 경우 사용자가 입력한 카테고리를 새 카테고리로 등록할지를 질의한다.
- [x] 저장 완료시 생성된 `id` 사용자에게 출력해야 한다.
    > `cmd_add`에서는 저장 후, `service.add_transaction`의 반환값인 새 `Transaction`의 `id`를 출력한다.

## 5. `list`(목록 조회)
- [x] `list`는 최신순으로 거래를 출력해야 한다.
    > `list`는 `BudgeService.latest()` 결과 값을 출력하는데, 이는 `heapq.nlargest`를 이용해 `iterable`(generator)한 `jsonl` 값 중 최신 순(`Transaction.sort_key` = (날짜, id번호)가 `높은 순`)으로 `limit`개만 출력하도록 한다.
- [x] `--limit N` 옵션을 지원해야 한다.(기본값 제공)
    > 마찬가지로, `heapq.nlargest`에 인자로 `N`값을 넘겨 내림차순으로 `N`개를 불러오도록 하며, `list` 명령어 등록 시 `add_argument()`를 통해 `default` 값을 20으로 등록해놓았다.
- [x] 제너레이터 기반 스트리밍 처리로 구현해야 한다.
    > `JSONL` 파일을 한 줄씩 읽어 `(줄 번호, dict)`를 `yield`하는 `iter_jsonl()` 함수를 사용해서 읽음

## 6. `update/delete`(수정/삭제)
- [x] `delete --id <id>`로 특정 거래를 삭제할 수 있어야 한다.
    > `service.delete_transaction(args.tx_id)`를 호출하면, `TransactionRepository.delete(tx_id)`를 호출해 저장소로부터 특정 거래를 삭제한다.
- [x] `존재하지 않는 id`는 "없는 데이터"로 처리하고 사용자 메시지를 출력해야 한다.
    > `TransactionRepository.delete(tx_id)`, `TransactionRepository.update(tx_id, transform)` 모두, 존재하지 않는 id에 대해 사용자 메시지를 담은 `NotFoundError`를 일으킨다.
- [x] `update`는 아래 중 하나의 방식으로 고정해 구현해야 한다.
  -  (안 A) `옵션 기반`
      > `date`, `type`, `category`, `amount`, `memo`, `tags` 옵션들을 매개변수로 받아 이를 반영한 update를 수행한다.

## 7. `search`(검색)
- [x] 조건 기반 검색을 지원해야 한다.
    > 입력받은 `--from`, `--to`, `--category`, `--type`, `--q`, `--tag`를 `SearchCriteria`라는 `dataclass`에 담은 뒤, `BudgetService.iter_matching()`의 인자로 넘겨 매치되는 `Transaction`만 검색한다.
- [x] 검색 결과는 최신순으로 출력해야 한다.
    > `BudgetService.search()`에서 `limit`이 있을 경우에는 `heapq.nlargest()`으로 최신순 `N`개를 뽑아내고, 그외에는 `sorted()`로 최신순 정렬된 목록을 뽑아낸다.
- [x] 스트리밍 처리(제너레이터 기반)를 유지해야 한다.
    > `search`에서 조건에 맞는 `Transaction`을 필터링할 때 `제너레이터`를 반환하는 `iter_all()`을 사용해 하나씩 불러온다.

## 8. `summary`(월별 요약)
- [x] `summary --month YYYY-MM` 입력을 받아 해당 월의 요약을 출력해야 한다.
    > `summary` 명령어가 `BudgetService.monthly_summary(args.month, args.top)`을 호출하고, `monthly_summary`는 `tx.month = args.month` 인 `Transaction`만 추려서 요약 출력한다.
- [x] 출력 항목
    ```bash
    # summary --month 2024-01 --top 3
    === 2024-01 월별 요약 ===
    항목    |        금액
    --------+------------
    총 수입 | 3,000,000원
    총 지출 |   169,500원
    잔액    | 2,830,500

    지출 TOP 3
    순위 | 카테고리 |      지출 |  비중
    -----+----------+-----------+------
    1)   | rent     | 150,000원 | 88.5%
    2)   | food     |  15,000원 |  8.8%
    3)   | cafe     |   4,500원 |  2.7%

    ```
- [x] 데이터가 없는 달은 “데이터 없음”을 명확히 출력한다.
    ```bash
    # summary --month 2023-05 ; echo "exit=$?"
    === 2023-05 월별 요약 ===
    데이터 없음 (해당 월에 등록된 거래가 없습니다)

    (예산 미설정 — `budget set --month 2023-05 --amount 금액` 으로 설정)
    exit=0
    ```

## 9. `budget`(예산)
- [x] `budget set --month YYYY-MM --amount <금액>`으로 월 예산을 저장해야 한다.
  ```bash
  # budget set --month 2024-01 --amount 500000
  [저장 완료] 2024-01 예산 500,000
  ```
- [x] `summary` 실행 시 예산이 설정되어 있으면 `예산 대비 사용률(%)`, `초과 여부(초과 시 경고 문구)` 를 함께 출력해야 한다.
  ```bash
  # budget set --month 2024-01 --amount 500000
  # summary --month 2024-01 --top 3
  === 2024-01 월별 요약 ===
  데이터 없음 (해당 월에 등록된 거래가 없습니다)

  예산: 500,000원 (사용률 0.0%) [--------------------]
  남은 예산: 500,000원
  ```
- [x] 예산 데이터도 반드시 영구 저장되어야 한다.
  > `datadir/budgets.jsonl`에 저장된다. `budget set` 명령어가 궁극적으로 `BudgetStore.set()`을 호출하게 되는데, 이때 `self.save()를 통해 실제 파일로 쓴다.

## 10. `category`(카테고리 관리)
- [x] `category add/list/remove`를 제공해야 한다.
  ```bash
  # category add
  root@1b9f4d31623d:/app# b category add # 대화형
  카테고리명: conv 
  [저장 완료] category=conv
  root@1b9f4d31623d:/app# b category add --name food
  [안내] 이미 등록된 카테고리입니다: food
  # category list
  root@1b9f4d31623d:/app# b category list
  - food
  - transport
  - rent
  - shopping
  - salary
  - allowance
  - etc
  - conv
  # category remove
  root@1b9f4d31623d:/app# b category remove # 대화형
  삭제할 카테고리명: rent
  [삭제 완료] category=rent
  root@1b9f4d31623d:/app# b category remove --name cafe ; echo "exit=$?"
  [오류] 'cafe' 카테고리가 없습니다.
  [힌트] `category list` 로 목록을 확인하세요.
  exit=3
  # category remove --replace-with another_category
  root@1b9f4d31623d:/app# b category add --name=cafe
  [저장 완료] category=cafe
  root@1b9f4d31623d:/app# b add
  날짜(YYYY-MM-DD, 엔터=오늘 2026-11-24): 2024-01-12
  타입(income/expense): expense
  카테고리: cafe
  금액(양수): 50000
  메모(선택): 
  태그(쉼표로 구분, 없으면 엔터): 
  [저장 완료] id=TX-000001
  root@1b9f4d31623d:/app# b category remove --name cafe --replace-with food
  [이동 완료] 거래 1건을 'food' 로 옮겼습니다.
  [삭제 완료] category=cafe
  root@1b9f4d31623d:/app# b search --category food
  ID        | 날짜       | 타입    | 카테고리 |   금액 | 메모 | 태그
  ----------+------------+---------+----------+--------+------+-----
  TX-000001 | 2024-01-12 | expense | food     | 50,000 |      |
  ```
- [x] 카테고리 삭제 시, 해당 카테고리를 사용하는 내역이 존재하면 삭제를 막거나, 대체 카테고리를 요구해야 한다.
  ```bash
  # 사용중인 카테고리는 삭제를 막고, 대체 카테고리를 지정하도록 유도함.
  root@1b9f4d31623d:/app# b category remove --name food
  [오류] 'food' 카테고리를 사용하는 거래 1건, 반복 규칙 0건이 있어 삭제할 수 없습니다.
  [힌트] --replace-with <대체카테고리> 옵션으로 옮길 카테고리를 지정하세요.
  ```

## 11. `import/export`(가져오기/내보내기)
- [x] `import --from \`로 거래를 일괄 등록한다.
  ```bash
  root@1b9f4d31623d:/app# b import --from examples/import_sample.csv
  [건너뜀] 5행: 등록되지 않은 카테고리 'unknown'
  [건너뜀] 6행: 날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).
  [건너뜀] 7행: 금액은 양의 정수여야 합니다: '-100'
  [완료] imported=4, skipped=3
  ```
- [x] `export --out \`로 조건에 맞는 거래를 CSV로 저장한다.
  ```bash
  # 2024-02에 발생한 거래들을 모두 내보낸다.
  root@1b9f4d31623d:/app# b export --out out/feb.csv --month 2024-02 ; cat out/feb.csv
  [완료] out/feb.csv (4 records)
  date,type,category,amount,memo,tags
  2024-02-01,income,allowance,100000,2월 용돈,
  2024-02-03,expense,food,8000,"김밥, 라면","meal,분식"
  2024-02-05,expense,transport,1500,버스,
  2024-02-10,expense,etc,2500,아이스크림,dessert
  # 2024-01-01 ~ 2024-01-31 사이에 발생한 거래들을 모두 내보낸다.
  root@1b9f4d31623d:/app# b export --out out/jan.csv --from 2024-01-01 --to 2024-01-31
  [완료] out/jan.csv (1 records)
  ```
- [x] `export`는 `--month YYYY-MM` 또는 `--from YYYY-MM-DD --to YYYY-MM-DD` 중 하나 이상 조건을 필수로 받는다.
  > 인자로 `--month` 또는 `--from, --to`가 주어지지 않을 경우, 이를 처리하는 `resolve_period(cli.py)` 함수에서 `ValidationError`를 발생시킨다.
- [x] `import/export`는 아래 CSV 최소 스키마를 고정한다.
  ```bash
  | column | required | 설명 |
  | --- | --- | --- |
  | date | Y | YYYY-MM-DD |
  | type | Y | income / expense |
  | category | Y | 등록된 카테고리 |
  | amount | Y | 양수 정수 |
  | memo | N | 문자열 |
  | tags | N | 쉼표(,) 구분 문자열 |
  | 공통: UTF-8, 헤더 포함 |   |   |
  ```
  > `export`시에는, csv 최상단에 `CSV_COLUMNS`(`tuple[str,...]: ("date", "type", "category", "amount", "memo", "tags")`)를 먼저 기입해 스키마를 고정시킨다.
  > `import`시에는, 매 row 데이터(`dict 타입`)를 사용해 `Transaction`을 생성하므로써 스키마를 고정시킨다.

## 보너스
1. 백업 기능
    - [x] `backup` 실행 시 타임스탬프가 포함된 백업 파일을 생성한다.
      ```bash
      # 백업 생성
      root@1b9f4d31623d:/app# b backup
      [백업 완료] tc/backups/backup-20261124-153545
      # 백업 목록 조회
      root@1b9f4d31623d:/app# b backup list
      - backup-20261124-153545
      # 백업 파일 이용해 복원
      root@1b9f4d31623d:/app# b backup restore --name backup-20261124-153545
      [복원 완료] backup-20261124-153545
      [안내] 복원 직전 상태는 backup-20261124-153825-before-restore 에 백업해 두었습니다.
      ```
2. 반복 내역 기능
    - [x] 월급/월세처럼 반복되는 내역을 등록하고, 특정 월에 자동 생성한다.
      ```bash
      # 반복 내역 등록
      root@1b9f4d31623d:/app# b recurring add # 기본은 대화형
      규칙 이름(예: 월급): 월급 
      타입(income/expense): income
      카테고리: salary
      금액(양수): 3000000
      매월 며칠(1~31): 25
      메모(선택, 엔터=규칙 이름): 
      태그(쉼표로 구분, 없으면 엔터): 
      [저장 완료] id=RC-000001 (매월 25일 salary 3,000,000원)
      ```
3. 출력 포맷 테이블 정렬
    - 외부 라이브러리 없이 문자열 정렬로 가독성을 개선한다.
    - 배움 포인트: 콘솔 UX + 포맷터 분리
4. 저장 원자성 강화
    - pdate/delete 시 임시 파일에 쓰고 rename으로 교체하는 방식을 적용한다.
    - 배움 포인트: 파일 기반 트랜잭션/원자성 사고
## 과제 목표

## 1. 실행 방법

```bash
# 프로젝트 폴더(budget_app 폴더가 보이는 위치)에서 실행
python -m budget_app --help            # 전체 명령 목록
python -m budget_app <command> --help  # 명령별 사용법
```

- 설치나 `pip install` 은 필요 없습니다.
- Windows 에서 `python` 대신 `py` 를 쓰는 경우: `py -m budget_app --help`

### 공통 옵션 (모든 명령에서 사용 가능)

| 옵션 | 설명 |
| --- | --- |
| `--datadir <폴더>` | 데이터 저장 폴더 (기본: `./data`) |
| `--verbose` | 실행 로그·실행 시간을 화면에도 출력 |
| `--help` | 사용법 출력 |

### 종료 코드

| 코드 | 의미 |
| --- | --- |
| 0 | 정상 종료 |
| 1 | 일반 오류 (입력 검증 실패, 사용 중 카테고리 삭제 시도 등) |
| 2 | 명령어/옵션 사용법 오류 |
| 3 | 데이터 없음 (없는 id, 없는 카테고리, 없는 파일/백업) |
| 4 | 저장소 오류 (파일 손상, 폴더 생성 실패) |
| 130 | 사용자가 Ctrl+C 로 중단 |

오류는 스택트레이스 없이 `[오류] 원인` + `[힌트] 해결 방법` 형식으로 출력됩니다.

## 2. 저장 파일 위치 / 형식

- 기본 위치: `./data/` (`--datadir` 로 변경)
- 형식: **JSONL** (한 줄에 JSON 객체 1개, UTF-8)

| 파일 | 내용 | 한 줄 예시 |
| --- | --- | --- |
| `transactions.jsonl` | 거래 내역 | `{"id": "TX-000001", "type": "expense", "date": "2024-01-15", "amount": 15000, "category": "food", "memo": "점심", "tags": ["meal"]}` |
| `categories.jsonl` | 카테고리 | `{"name": "food"}` |
| `budgets.jsonl` | 월 예산 | `{"month": "2024-01", "amount": 500000}` |
| `recurring.jsonl` | 반복 내역 규칙 (보너스) | `{"id": "RC-000001", "name": "월급", "type": "income", "category": "salary", "amount": 3000000, "day": 25, ...}` |
| `app.log` | 실행 로그 (시작/완료/실패/실행 시간) | |
| `backups/backup-YYYYMMDD-HHMMSS/` | 백업 폴더 (보너스) | |

### 초기 실행 정책
- 저장 폴더·파일이 없으면 **자동 생성**하고 `[안내]` 메시지를 출력합니다.
- 카테고리 파일이 비어 있으면 **(안 A) 기본 카테고리 자동 생성**:
  `food, transport, rent, shopping, salary, allowance, etc`

### 데이터 규칙
- `id`: `TX-000001` 형식, 자동 부여 (명령에서 `TX-000001`, `tx-1`, `1` 모두 허용)
- `type`: `income` / `expense` (입력 시 `수입` / `지출` 도 허용)
- `date`: `YYYY-MM-DD` (존재하지 않는 날짜는 거부)
- `amount`: 양의 정수 (`15,000` 처럼 쉼표 입력 허용)
- `category`: 등록된 카테고리만 허용 (소문자로 정리)
- `tags`: 쉼표 구분, 공백·중복 자동 제거

## 3. 주요 명령 예시

### 거래 추가 (대화형)
```text
$ python -m budget_app add
날짜(YYYY-MM-DD, 엔터=오늘 2026-10-29): 2024-01-15
타입(income/expense): expense
카테고리: food
금액(양수): 15000
메모(선택): 점심
태그(쉼표로 구분, 없으면 엔터): meal
[저장 완료] id=TX-000001
```
잘못된 값은 오류 메시지 후 다시 묻습니다. 없는 카테고리를 입력하면 등록 여부를 물어봅니다.

### 목록 / 검색
```bash
python -m budget_app list --limit 10                     # 최신순 10건 (기본 20)
python -m budget_app search --from 2024-01-01 --to 2024-01-31
python -m budget_app search --month 2024-01 --type expense --category food
python -m budget_app search --q 점심 --tag meal --limit 5
```

### 월별 요약 + 예산
```bash
python -m budget_app budget set --month 2024-01 --amount 500000
python -m budget_app budget get --month 2024-01
python -m budget_app budget list
python -m budget_app summary --month 2024-01 --top 3
```
- 예산 설정 시 사용률(%)과 진행 막대를 표시
- 80% 이상: `[주의]`, 초과 시: `[경고] 예산을 N원 초과했습니다!`
- 거래가 없는 달: `데이터 없음`

### 카테고리
```bash
python -m budget_app category add              # 대화형 (카테고리명: ...)
python -m budget_app category add --name cafe
python -m budget_app category list
python -m budget_app category remove --name cafe
python -m budget_app category remove --name cafe --replace-with food
```
사용 중인 카테고리는 그냥 삭제할 수 없고, `--replace-with` 로 대체 카테고리를 지정해야 합니다
(해당 거래와 반복 규칙이 대체 카테고리로 옮겨진 뒤 삭제).

### 수정 / 삭제
`update` 는 **옵션 기반(안 A)** 으로 고정되어 있습니다. 지정한 항목만 바뀝니다.
```bash
python -m budget_app update --id TX-000001 --amount 18000 --memo "점심 (수정)"
python -m budget_app update --id 1 --tags ""      # 태그 비우기
python -m budget_app delete --id TX-000001
```
없는 id 는 `[오류] id=... 거래를 찾을 수 없습니다 (없는 데이터).` 출력 후 종료 코드 3.

### 가져오기 / 내보내기
```bash
python -m budget_app import --from examples/import_sample.csv
python -m budget_app export --out export.csv --month 2024-01
python -m budget_app export --out export.csv --from 2024-01-01 --to 2024-03-31
```
- `export` 는 `--month` 또는 `--from`/`--to` 중 하나 이상 필수 (둘을 섞으면 오류)
- `import` 는 잘못된 행을 건너뛰고 이유를 표시: `[완료] imported=4, skipped=3`

### 보너스 기능
```bash
# 1) 백업
python -m budget_app backup                     # = backup create
python -m budget_app backup list
python -m budget_app backup restore --name backup-20261029-080126

# 2) 반복 내역
python -m budget_app recurring add              # 대화형 (이름/타입/카테고리/금액/매월 며칠)
python -m budget_app recurring list
python -m budget_app recurring apply --month 2024-02
python -m budget_app recurring remove --id RC-000001
```
- 복원 직전 상태는 `...-before-restore` 백업으로 자동 보관됩니다.
- 반복 내역은 같은 달에 두 번 `apply` 해도 중복 생성되지 않습니다. 31일 규칙은 짧은 달엔 말일로 생성됩니다.
- 3) 테이블 정렬: 한글 폭(2칸)을 계산해 표가 정렬됩니다. 4) 저장 원자성: 아래 참고.

## 4. import / export CSV 스키마

| column | required | 설명 |
| --- | --- | --- |
| date | Y | YYYY-MM-DD |
| type | Y | income / expense |
| category | Y | 등록된 카테고리 |
| amount | Y | 양수 정수 |
| memo | N | 문자열 |
| tags | N | 쉼표(,) 구분 문자열 (CSV 에서는 `"meal,lunch"` 처럼 따옴표로 감쌈) |

- 공통: UTF-8, 헤더 포함 (엑셀의 UTF-8 BOM 도 자동 처리)
- `id` 는 CSV 에 포함하지 않으며, 가져올 때 새로 부여됩니다.

예시 (`examples/import_sample.csv`):
```csv
date,type,category,amount,memo,tags
2024-02-01,income,allowance,100000,2월 용돈,
2024-02-03,expense,food,8000,"김밥, 라면","meal,분식"
```

## 5. 설계 요약

| 모듈 | 계층 | 책임 |
| --- | --- | --- |
| `models.py` | 모델 | `Transaction`, `RecurringRule` dataclass, 입력 검증 함수 |
| `storage.py` | 저장소 | JSONL 스트리밍 읽기, 원자적 쓰기, `TransactionRepository` / `CategoryStore` / `BudgetStore` / `RecurringStore` |
| `services.py` | 서비스 | `BudgetService` — 추가/검색/요약/카테고리 규칙/CSV/백업/반복 내역 |
| `cli.py` | CLI | argparse 명령 정의, 대화형 입력, 출력 |
| `decorators.py` | 공통 | `@handle_errors`, `@log_execution`, `@timed` |
| `formatter.py` | 출력 | 한글 폭을 고려한 테이블 정렬, 금액 표시 |
| `errors.py` | 공통 | `AppError`(원인+힌트) 계열 예외 |

- **스트리밍**: `list`, `search`, `summary`, `export`, `update`, `delete` 모두 파일을 한 줄씩 읽는 제너레이터를 사용합니다.
  `list --limit N` 은 `heapq.nlargest` 로 상위 N건만 메모리에 유지합니다. (30만 건/38MB 파일에서 최대 메모리 약 150KB)
- **원자적 저장**: `update/delete/카테고리/예산/export/restore` 는 임시 파일에 쓴 뒤 `os.replace()` 로 교체하므로,
  도중에 프로그램이 죽어도 원본이 깨지지 않습니다. `add`/`import` 는 파일 끝에 추가(append)합니다.
