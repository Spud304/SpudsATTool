"""Fan-out of live scrim messages between workers: Redis pub/sub in dev and prod, in-process queues in tests.

Publishing is synchronous (called from request handlers after commit); subscribing is async (the SSE view).
"""

import asyncio
import json
import threading
from typing import Any, Protocol

from django.conf import settings


class Subscription(Protocol):
    async def open(self) -> None: ...

    async def get(self, timeout: float) -> dict | None:
        """Next message, or None once `timeout` seconds pass without one."""
        ...

    async def close(self) -> None: ...


class Broker(Protocol):
    def publish(self, session_id: int, message: dict) -> None: ...

    def subscribe(self, session_id: int) -> Subscription: ...


def channel(session_id: int) -> str:
    return f"scrim:{session_id}"


# memory (tests, single process)


class _MemorySubscription:
    def __init__(self, broker: "MemoryBroker", session_id: int):
        self.broker = broker
        self.session_id = session_id
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def open(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.broker._add(self)

    async def get(self, timeout: float) -> dict | None:
        try:
            return await asyncio.wait_for(self.queue.get(), timeout)
        except TimeoutError:
            return None

    async def close(self) -> None:
        self.broker._remove(self)

    def deliver(self, message: dict) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, message)


class MemoryBroker:
    def __init__(self) -> None:
        self._subs: dict[int, set[_MemorySubscription]] = {}
        self._lock = threading.Lock()
        self.published: list[tuple[int, dict]] = []

    def publish(self, session_id: int, message: dict) -> None:
        self.published.append((session_id, message))
        with self._lock:
            subs = list(self._subs.get(session_id, ()))
        for sub in subs:
            sub.deliver(message)

    def subscribe(self, session_id: int) -> _MemorySubscription:
        return _MemorySubscription(self, session_id)

    def _add(self, sub: _MemorySubscription) -> None:
        with self._lock:
            self._subs.setdefault(sub.session_id, set()).add(sub)

    def _remove(self, sub: _MemorySubscription) -> None:
        with self._lock:
            self._subs.get(sub.session_id, set()).discard(sub)

    def subscriber_count(self, session_id: int) -> int:
        with self._lock:
            return len(self._subs.get(session_id, ()))


# redis


class _RedisSubscription:
    def __init__(self, url: str, session_id: int):
        self.url = url
        self.name = channel(session_id)
        self._client: Any = None
        self._pubsub: Any = None

    async def open(self) -> None:
        import redis.asyncio as aredis

        self._client = aredis.Redis.from_url(self.url)
        self._pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(self.name)

    async def get(self, timeout: float) -> dict | None:
        raw = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if raw is None or raw.get("type") != "message":
            return None
        return json.loads(raw["data"])

    async def close(self) -> None:
        try:
            await self._pubsub.unsubscribe(self.name)
            await self._pubsub.aclose()
        finally:
            await self._client.aclose()


class RedisBroker:
    def __init__(self, url: str):
        self.url = url
        self._sync: Any = None
        self._lock = threading.Lock()

    def publish(self, session_id: int, message: dict) -> None:
        import redis

        with self._lock:
            if self._sync is None:
                self._sync = redis.Redis.from_url(self.url)
        self._sync.publish(channel(session_id), json.dumps(message))

    def subscribe(self, session_id: int) -> _RedisSubscription:
        return _RedisSubscription(self.url, session_id)


_broker: Broker | None = None
_broker_lock = threading.Lock()


def get_broker() -> Broker:
    global _broker
    with _broker_lock:
        if _broker is None:
            if getattr(settings, "SCRIM_BROKER", "redis") == "memory":
                _broker = MemoryBroker()
            else:
                _broker = RedisBroker(settings.REDIS_URL)
        return _broker


def reset_broker() -> None:
    """Tests: drop the singleton so each test starts with an empty in-memory broker."""
    global _broker
    with _broker_lock:
        _broker = None
