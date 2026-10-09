"""In-process event bus for WebSocket fan-out.

A bounded queue per subscriber ensures a slow browser client cannot block the
supervisory control loop.  Events dropped due to back-pressure are counted so
the dashboard can surface the condition rather than silently losing data.
"""

from __future__ import annotations

import asyncio
from typing import Any

MAX_QUEUE = 500


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self.dropped = 0

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, message: dict[str, Any]) -> None:
        """Non-blocking publish; drops the message for full queues."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                self.dropped += 1
