# Data 코드 작성 지침

이 파일은 `data/` 디렉터리와 그 하위 경로의 코드 생성·수정에 적용한다.

## 주석 및 도큐스트링

- 새로 작성하거나 수정하는 Python 코드의 모듈, 주요 함수, 클래스 도큐스트링은 한국어로 작성한다.
- 비직관적인 데이터 규칙, 보안 제약, 파티셔닝 기준, 멱등성, 재처리 조건, 예외 처리 이유는 한국어 주석으로 설명한다.
- 주석은 단순히 코드가 무엇을 하는지 반복하기보다 왜 그 방식이 필요한지 설명한다.
- 단순 대입, 명확한 반복문, 자명한 라이브러리 호출에는 불필요한 주석을 달지 않는다.
- API 필드명(`basDt` 등), 클래스/함수/변수명, SQL 식별자, 환경변수, Azure 서비스명, 로그 키는 기존 영문 표기를 유지한다.
- 오류 메시지와 CLI 옵션은 운영/자동화 호환성을 위해 기존 언어와 형식을 임의로 바꾸지 않는다.

## 데이터 계층별 우선 설명 대상

- Raw: 원본 불변성, `basDt` 기준 월 파티션, content-addressed hash, 중복 저장 방지
- PostgreSQL: 관계형 제약, UPSERT 충돌키, transaction/rollback, membership 데이터 보호
- Processed: schema version, 재생성 가능성, 기간/월 파티션
- Features: look-ahead 방지, rolling window 경계, feature version, warm-up 기간
- Azure: Entra ID/DefaultAzureCredential 우선, Shared Key 금지, Blob 재시도/멱등성
- Alembic: 과거 migration은 현재 ORM에 의존하지 않도록 self-contained하게 유지하고 destructive 변경 이유를 한국어로 기록

## 코드 생성 시 확인

1. 구현 전에 기존 데이터 저장 원칙과 경로 규칙을 확인한다.
2. 핵심 의사결정이 코드만으로 명확하지 않으면 한국어 주석을 추가한다.
3. 주석 추가를 이유로 API payload, 데이터 타입, 경로, hash, SQL 동작을 변경하지 않는다.
4. 변경 후 `python -m pytest tests -q`를 실행해 기존 동작이 유지되는지 확인한다.
