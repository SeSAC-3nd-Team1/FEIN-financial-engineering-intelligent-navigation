# Model Raw Collection Summary

- 테스트 기간: 2026-08-19 ~ 2026-08-26
- 총 실행 시간: 12.537초
- 전체 신규/검증 row: 5,665
- 평균 처리량: 451.85 rows/s
- 병목 source: krx
- OpenDART company limit: 없음(전체)

## Source별 성능

| Source | Concurrency | API calls | Rows | Download(s) | Upload(s) | Rows/s | Upload MB/s | New blobs | Skipped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| krx | 4 | 7 | 5,665 | 6.511 | 0.572 | 870.03 | 0.92 | 7 | 4 |
| ecos-bok | 2 | 0 | 0 | 0.000 | 0.000 | 0.00 | 0.00 | 0 | 0 |
| opendart | 1 | 0 | 0 | 0.000 | 0.000 | 0.00 | 0.00 | 0 | 0 |

## 적용 방식

- 월/기간 partition 단위로 누락 작업만 계산하고 source별 bounded worker를 사용한다.
- KRX·ECOS는 canonical JSONL gzip, OpenDART는 provider 원문 bytes를 content hash 경로로 저장한다.
- 성공 partition만 `_manifests/model_raw_coverage.json`에 기록하며 실제 Blob prefix와 교차검증한다.
- 수집과 업로드가 worker 안에서 연속 실행되어 다른 worker의 네트워크 대기와 겹친다.
- 429/5xx는 각 공통 client의 제한된 exponential backoff를 사용한다.
