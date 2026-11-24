from datetime import datetime, timezone


def report_summary(rows: list, target_cents: int = 5_000_000) -> dict:
    volume = sum(int(row["amount_cents"]) for row in rows)
    return {
        "recorded_volume_cents": volume,
        "recorded_count": len(rows),
        "daily_volume_target_cents": target_cents,
        "target_is_actual": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
