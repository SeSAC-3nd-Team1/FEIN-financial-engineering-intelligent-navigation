from datetime import date
from decimal import Decimal

from app.services.rebalancing_identity import proposal_key


def test_proposal_key_is_stable_for_same_server_snapshot() -> None:
    values = (
        "low",
        "005930",
        "SELL",
        Decimal("20.00"),
        Decimal("15.00"),
        Decimal("5.00"),
        Decimal("50000.00"),
        date(2026, 8, 25),
    )

    assert proposal_key(*values) == proposal_key(*values)
    assert proposal_key(*values).startswith("low|005930|SELL|")


def test_proposal_key_changes_when_proposal_snapshot_changes() -> None:
    base = (
        "low",
        "005930",
        "SELL",
        Decimal("20.00"),
        Decimal("15.00"),
        Decimal("5.00"),
        Decimal("50000.00"),
        date(2026, 8, 25),
    )

    changed = (*base[:-1], date(2026, 8, 26))

    assert proposal_key(*base) != proposal_key(*changed)
