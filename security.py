import time
from collections import defaultdict, deque


class ActivityGuard:
    """In-memory, short-window abuse detection; restart safe and transparent."""

    def __init__(self) -> None:
        self.message_times: dict[int, deque[float]] = defaultdict(deque)
        self.join_times: deque[float] = deque(maxlen=1000)

    def check_message(self, user_id: int, mentions: int, now: float | None = None) -> str | None:
        now = now or time.monotonic()
        bucket = self.message_times[user_id]
        bucket.append(now)
        while bucket and now - bucket[0] > 10:
            bucket.popleft()
        if len(bucket) >= 7:
            return "message_flood"
        if mentions >= 6:
            return "mention_spam"
        return None

    def check_join(self, now: float | None = None) -> bool:
        now = now or time.monotonic()
        self.join_times.append(now)
        while self.join_times and now - self.join_times[0] > 60:
            self.join_times.popleft()
        return len(self.join_times) >= 12
