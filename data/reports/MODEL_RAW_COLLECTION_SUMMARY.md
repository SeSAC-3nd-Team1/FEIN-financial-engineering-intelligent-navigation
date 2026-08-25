# Model Raw Collection Summary

- 테스트 기간: 2026-08-01 ~ 2026-08-24
- 총 실행 시간: 120.997초
- 전체 신규/검증 row: 97,382
- 평균 처리량: 804.83 rows/s
- 병목 source: opendart
- OpenDART company limit: 1 (해당 기간에는 재무 분기말이 없어 공시 수집량에는 영향 없음)

## Source별 성능

| Source | Concurrency | API calls | Rows | Download(s) | Upload(s) | Rows/s | Upload MB/s | New blobs | Skipped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| krx | 4 | 112 | 87,616 | 69.053 | 7.906 | 1,268.82 | 0.00 | 0 | 0 |
| ecos-bok | 2 | 5 | 67 | 1.132 | 0.117 | 59.19 | 0.02 | 2 | 0 |
| opendart | 1 | 98 | 9,699 | 85.282 | 2.236 | 113.73 | 0.99 | 98 | 1 |

## 적용 방식

- 월/기간 partition 단위로 누락 작업만 계산하고 source별 bounded worker를 사용한다.
- KRX·ECOS는 canonical JSONL gzip, OpenDART는 provider 원문 bytes를 content hash 경로로 저장한다.
- 성공 partition만 `_manifests/model_raw_coverage.json`에 기록하며 실제 Blob prefix와 교차검증한다.
- 수집과 업로드가 worker 안에서 연속 실행되어 다른 worker의 네트워크 대기와 겹친다.
- 429/5xx는 각 공통 client의 제한된 exponential backoff를 사용한다.
