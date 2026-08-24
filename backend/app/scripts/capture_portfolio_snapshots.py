"""활성 가상계좌의 일별 포트폴리오 스냅샷을 저장한다."""

from app.db.session import SessionLocal
from app.services.portfolio import PortfolioService


def main() -> None:
    with SessionLocal() as session:
        captured = PortfolioService(session).capture_daily_snapshots()
    print(f"captured_portfolio_snapshots={captured}")


if __name__ == "__main__":
    main()
