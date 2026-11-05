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
  > `@dataclass`란, 사용자 정의 클래스에 `__init__`, `__repr__`와 같은 `보일러플레이트 메서드 자동 생성`, `프로퍼티 선언 가독성 향상 및 디폴트 값 세팅을 가능`하게해주는 데코레이터
- [x] 최소 2개 이상의 클래스를 사용한다
  > `models.py`: Transaction
  > `services.py`: SearchCriteria, MonthlySummary, ImportResult, ApplyResult, BudgetService
  > `storage.py`: JsonlTable, TransactionRepository, CategoryStore, BudgetStore, RecurringStore
- [x] 입력 검증
  > `models.py`의 `parse_*` 함수들이 입력을 검증함

## 3. 저장 정책
- [x] 저장 포맷은 JSONL 또는 CSV 중 1개를 선택한다.
  > 
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
