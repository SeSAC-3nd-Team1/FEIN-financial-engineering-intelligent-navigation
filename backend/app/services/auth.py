"""회원가입과 인증 service."""

from datetime import UTC, date, datetime
import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import Term, User, UserAgreement
from app.schemas.api import LoginRequest, SignupRequest
from app.services.email_verification import EmailTokenReservation, EmailVerificationService


SIGNUP_TERM_CODES = (
    "B_PRIVACY",
    "C_ASSOCIATE_TERMS",
    "AI_PERSONALIZATION",
)

# 미성년자(만 19세 미만, 민법상 성년 기준)는 법정대리인 동의 없이 서비스 이용계약을 체결할 수
# 없다(민법 제5조). 가입 흐름에 법정대리인 동의 절차가 없어, 가입 가능한 최소 연령을 만 19세로 둔다.
MIN_SIGNUP_AGE = 19

logger = logging.getLogger(__name__)


def _calculate_age(birthdate: str) -> int:
    """YYMMDD(세기 구분 없음)로부터 만 나이를 계산한다.

    20YY로 해석했을 때 미래 날짜가 되면 19YY로 본다 — 프런트(lib/validation.ts)와 동일한 규칙.
    """
    yy, mm, dd = int(birthdate[0:2]), int(birthdate[2:4]), int(birthdate[4:6])
    today = datetime.now(UTC).date()
    year = 2000 + yy
    try:
        born = date(year, mm, dd)
    except ValueError as exc:
        raise ServiceError("INVALID_BIRTHDATE", "생년월일이 올바르지 않습니다.") from exc
    if born > today:
        year = 1900 + yy
        try:
            born = date(year, mm, dd)
        except ValueError as exc:
            raise ServiceError("INVALID_BIRTHDATE", "생년월일이 올바르지 않습니다.") from exc
    age = today.year - born.year
    if (today.month, today.day) < (born.month, born.day):
        age -= 1
    return age


class AuthService:
    def __init__(
        self,
        session: Session,
        email_verification: EmailVerificationService | None = None,
    ) -> None:
        self.session = session
        self.email_verification = email_verification

    def signup(self, request: SignupRequest) -> User:
        duplicate = self.session.scalar(
            select(User).where(or_(User.user_id == request.user_id, User.email == request.email.lower()))
        )
        if duplicate:
            raise ServiceError("DUPLICATE_ACCOUNT", "이미 사용 중인 아이디 또는 이메일입니다.", 409)
        if _calculate_age(request.birthdate) < MIN_SIGNUP_AGE:
            raise ServiceError(
                "UNDERAGE",
                f"만 {MIN_SIGNUP_AGE}세 이상만 가입할 수 있습니다.",
            )
        catalog = self.signup_terms()
        catalog_by_key = {(term.term_code, term.version): term for term in catalog}
        if any((item.term_code, item.version) not in catalog_by_key for item in request.agreements):
            raise ServiceError("INVALID_TERM_VERSION", "존재하지 않는 약관 또는 버전입니다.")
        accepted = {(item.term_code, item.version) for item in request.agreements if item.agreed}
        required = {(term.term_code, term.version) for term in catalog if term.is_required}
        if not required.issubset(accepted):
            raise ServiceError("REQUIRED_TERMS_NOT_AGREED", "필수 약관에 모두 동의해야 합니다.")
        if self.email_verification is None:
            raise ServiceError(
                "EMAIL_VERIFICATION_UNAVAILABLE",
                "이메일 인증 서비스를 사용할 수 없습니다.",
                503,
            )
        reservation = self.email_verification.reserve_token(
            request.email_verification_token,
            request.email.lower(),
        )
        now = datetime.now(UTC)
        try:
            user = User(
                user_id=request.user_id,
                password_hash=hash_password(request.password),
                name=request.name.strip(),
                birthdate=request.birthdate,
                phone_number=request.phone_number,
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
        except Exception:
            self.session.rollback()
            self._release_email_reservation(reservation)
            raise
        try:
            self.email_verification.finalize_token(reservation)
        except Exception:
            # 회원 생성 transaction이 이미 확정된 뒤이므로 성공 응답을 뒤집지 않는다.
            # 예약 상태는 Redis TTL이 만료시키며 같은 토큰의 재사용은 계속 차단된다.
            logger.warning("Email verification token finalization failed user_id=%s", user.id)
        return user

    def _release_email_reservation(self, reservation: EmailTokenReservation) -> None:
        try:
            if self.email_verification is not None:
                self.email_verification.release_token(reservation)
        except Exception:
            logger.warning("Email verification token release failed")

    def signup_terms(self) -> list[Term]:
        """각 약관 코드에서 현재 효력이 있는 최신 버전만 반환한다."""
        now = datetime.now(UTC)
        terms = self.session.scalars(
            select(Term)
            .where(Term.term_code.in_(SIGNUP_TERM_CODES), Term.effective_at <= now)
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
