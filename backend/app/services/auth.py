"""회원가입과 인증 service."""

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Term, User, UserAgreement
from app.schemas.api import LoginRequest, SignupRequest


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def signup(self, request: SignupRequest) -> User:
        if not request.phone_verified or not request.email_verified:
            raise ServiceError("VERIFICATION_REQUIRED", "휴대폰과 이메일 인증이 필요합니다.")
        duplicate = self.session.scalar(
            select(User).where(or_(User.user_id == request.user_id, User.email == request.email.lower()))
        )
        if duplicate:
            raise ServiceError("DUPLICATE_ACCOUNT", "이미 사용 중인 아이디 또는 이메일입니다.", 409)
        catalog = self.signup_terms()
        catalog_by_key = {(term.term_code, term.version): term for term in catalog}
        if any((item.term_code, item.version) not in catalog_by_key for item in request.agreements):
            raise ServiceError("INVALID_TERM_VERSION", "존재하지 않는 약관 또는 버전입니다.")
        accepted = {(item.term_code, item.version) for item in request.agreements if item.agreed}
        required = {(term.term_code, term.version) for term in catalog if term.is_required}
        if not required.issubset(accepted):
            raise ServiceError("REQUIRED_TERMS_NOT_AGREED", "필수 약관에 모두 동의해야 합니다.")
        now = datetime.now(UTC)
        try:
            user = User(
                user_id=request.user_id,
                password_hash=hash_password(request.password),
                name=request.name.strip(),
                birthdate=request.birthdate,
                phone_number=request.phone_number,
                phone_verified_at=now,
                email=request.email.lower(),
                email_verified_at=now,
                member_type="ASSOCIATE",
                account_status="ACTIVE",
            )
            self.session.add(user)
            self.session.flush()
            for item in request.agreements:
                term = catalog_by_key[(item.term_code, item.version)]
                self.session.add(UserAgreement(
                    user_id=user.id, term_id=term.id, is_agreed=item.agreed,
                    agreed_at=now if item.agreed else None,
                ))
            self.session.commit()
            self.session.refresh(user)
        except Exception:
            self.session.rollback()
            raise
        return user

    def signup_terms(self) -> list[Term]:
        """각 약관 코드에서 현재 효력이 있는 최신 버전만 반환한다."""
        now = datetime.now(UTC)
        terms = self.session.scalars(
            select(Term)
            .where(Term.effective_at <= now)
            .order_by(Term.term_code, Term.effective_at.desc(), Term.id.desc())
        )
        latest: dict[str, Term] = {}
        for term in terms:
            latest.setdefault(term.term_code, term)
        catalog = list(latest.values())
        if not any(term.is_required for term in catalog):
            raise ServiceError(
                "TERMS_CATALOG_UNAVAILABLE",
                "현재 사용할 수 있는 필수 약관이 준비되지 않았습니다.",
                503,
            )
        return catalog

    def login(self, request: LoginRequest) -> str:
        user = self.session.scalar(select(User).where(User.user_id == request.user_id))
        if not user or not verify_password(request.password, user.password_hash):
            raise ServiceError("INVALID_CREDENTIALS", "아이디 또는 비밀번호가 올바르지 않습니다.", 401)
        if user.account_status != "ACTIVE":
            raise ServiceError("ACCOUNT_INACTIVE", "사용할 수 없는 회원 계정입니다.", 403)
        user.last_login_at = datetime.now(UTC)
        self.session.commit()
        return create_access_token(user.id)
