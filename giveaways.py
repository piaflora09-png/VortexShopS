import secrets


def choose_winner(user_ids: list[int]) -> int | None:
    if not user_ids:
        return None
    return secrets.choice(sorted(set(user_ids)))
