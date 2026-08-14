from datetime import date

from scripts.backfill_public_data_history import (
    ISSUANCE_STATUS_OPERATION,
    build_commands,
)


def test_history_backfill_runs_range_operations_before_daily_issuance() -> None:
    commands = build_commands(
        start_date=date(2016, 8, 14),
        end_date=date(2021, 8, 13),
        rows=10_000,
        progress_every=25,
    )

    assert len(commands) == 2
    exclude_index = commands[0].index("--exclude-operation")
    assert commands[0][exclude_index + 1] == ISSUANCE_STATUS_OPERATION
    assert "--all-pages" in commands[0]
    assert commands[1][1].endswith("backfill_issuance_status.py")
    assert "2016-08-14" in commands[0]
    assert "2021-08-13" in commands[1]
