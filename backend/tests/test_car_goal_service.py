"""목표 차량 current_amount가 저장된 값이 아니라 실제 계좌 평가액에서만 나오는지 검증한다."""

from decimal import Decimal
from types import SimpleNamespace

from app.core.errors import NotFoundError
from app.services.car_goal import CarGoalService


class FakeSession:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []

    def get(self, model, pk):
        return self.existing

    def add(self, value) -> None:
        self.added.append(value)
        self.existing = value

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, value) -> None:
        self.refreshed.append(value)


class FakeAccounts:
    def __init__(self, account=None, error: Exception | None = None) -> None:
        self.account = account
        self.error = error
        self.calls = []

    def get_mine(self, user_id, operation_mode):
        self.calls.append((user_id, operation_mode))
        if self.error is not None:
            raise self.error
        return self.account


class FakePortfolio:
    def __init__(self, total_assets: Decimal) -> None:
        self.total_assets = total_assets
        self.calls = []

    def evaluate(self, user_id, account_id):
        self.calls.append((user_id, account_id))
        return SimpleNamespace(total_assets=self.total_assets)


def _user(user_id: int = 7, mode: str = "SEMI_AUTO"):
    return SimpleNamespace(id=user_id, active_operation_mode=mode)


def test_upsert_ignores_client_current_amount_and_uses_real_portfolio_value() -> None:
    """upsert는 애초에 current_amount를 인자로 받지 않는다 — 실제 활성 계좌의
    포트폴리오 평가액(total_assets)만 저장돼야 한다."""

    session = FakeSession()
    service = CarGoalService(session)
    service.accounts = FakeAccounts(account=SimpleNamespace(id="acc-1"))
    service.portfolio = FakePortfolio(total_assets=Decimal("12345678.90"))

    goal = service.upsert(_user(), "HIGHEND", Decimal("50000000"))

    assert goal.current_amount == Decimal("12345678.90")
    assert service.accounts.calls == [(7, "SEMI_AUTO")]
    assert service.portfolio.calls == [(7, "acc-1")]
    assert session.commits == 1


def test_upsert_defaults_current_amount_to_zero_without_an_account_yet() -> None:
    """해당 운용방식 계좌가 아직 없으면(가입 직후) 0원으로 취급하고 포트폴리오는 조회하지 않는다."""

    session = FakeSession()
    service = CarGoalService(session)
    service.accounts = FakeAccounts(error=NotFoundError("ACCOUNT_NOT_FOUND", "없음"))
    service.portfolio = FakePortfolio(total_assets=Decimal("999999"))

    goal = service.upsert(_user(), "INEX", Decimal("10000000"))

    assert goal.current_amount == Decimal("0")
    assert service.portfolio.calls == []


def test_get_recomputes_current_amount_instead_of_trusting_stored_value() -> None:
    """DB에 남아있는 값(과거 요청으로 저장됐을 수 있는 값)을 그대로 응답하지 않고,
    조회 시점에 실제 계좌를 다시 평가한 값으로 덮어써야 한다."""

    existing = SimpleNamespace(
        user_id=7,
        car_grade="INEX",
        goal_amount=Decimal("10000000"),
        current_amount=Decimal("999999999"),
    )
    session = FakeSession(existing=existing)
    service = CarGoalService(session)
    service.accounts = FakeAccounts(account=SimpleNamespace(id="acc-1"))
    service.portfolio = FakePortfolio(total_assets=Decimal("3000000"))

    goal = service.get(_user())

    assert goal.current_amount == Decimal("3000000")
    assert goal is existing
