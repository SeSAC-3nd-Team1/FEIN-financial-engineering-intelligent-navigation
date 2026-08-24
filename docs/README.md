# Documentation

코드와 함께 버전 관리가 필요한 프로젝트 기술 문서를 관리한다.

## 현재 기준 문서

- [환경 변수 관리 가이드](ENVIRONMENT_VARIABLES.md)
- [Azure PostgreSQL 단일 프로젝트 DB 가이드](AZURE_POSTGRESQL_DEV.md)
- [현재 PostgreSQL 데이터 명세](DATABASE_SPECIFICATION.md)
- [Backend API 명세](BACKEND_API_SPECIFICATION.md)
- [투자성향 AI 분석 API 명세](INVESTOR_PROFILE_API_SPECIFICATION.md)
- [KIS 실시간 시장가 및 차트 API 명세](KIS_REALTIME_MARKET_API_SPECIFICATION.md)
- [가상투자 PostgreSQL 데이터 명세](VIRTUAL_TRADING_DATA_SPECIFICATION.md)
- [가상투자 ERD](VIRTUAL_TRADING_ERD.md)
- [Frontend → API → DB 매핑](FRONTEND_API_DB_MAPPING.md)
- [데이터 아키텍처](DATA_ARCHITECTURE.md)
- [데이터 레이어 운영](DATA_LAYER_OPERATIONS.md)
- [회원가입 PostgreSQL 상세 설계](../data/REGISTRATION_DB.md)
- [회원가입 데이터 명세](REGISTRATION_DATA_SPECIFICATION.md)
- [회원가입 ERD](REGISTRATION_DATA_ERD.md)
- [금융 데이터 파이프라인](../data/docs/FINANCIAL_DATA_PIPELINE.md)
- [금융 데이터 파이프라인 Runbook](../data/docs/FINANCIAL_PIPELINE_RUNBOOK.md)
- [모델링 Dataset Card](../data/docs/MODELING_DATASET_CARD.md)
- [Feature Dictionary](../data/docs/FEATURE_DICTIONARY.md)

## 역사 문서

완료된 migration/retirement 당시의 상태를 증거로 남겨야 하는 문서는 `docs/archive/`에 보관한다. archive 문서는 현재 운영 구조의 source of truth가 아니며, 당시 실행 결과나 의사결정 이력을 확인할 때만 사용한다.

현재 코드/운영 구조와 문서가 충돌하면 실행 코드, Alembic head, canonical Azure Blob path를 우선 확인하고 문서를 함께 갱신한다.
