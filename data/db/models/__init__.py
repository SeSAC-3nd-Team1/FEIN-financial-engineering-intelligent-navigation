"""Alembic과 애플리케이션이 공통으로 import하는 ORM model registry다.

금융/API PostgreSQL schema를 재설계하는 동안 해당 모델은 의도적으로 등록하지 않는다.
현재 영구 보존 대상인 membership 모델만 registry에 포함해 금융 구조 정리 작업이
회원가입 데이터에 영향을 주지 않게 한다.
"""

from db.models.membership import Term, User, UserAgreement

__all__ = ["Term", "User", "UserAgreement"]
