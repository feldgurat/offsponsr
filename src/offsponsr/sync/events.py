"""Carries news from the background work to whoever is listening (the UI, over SSE)."""

from __future__ import annotations

import queue
import threading
from typing import Any

Event = dict[str, Any]


class Listener:
    """One subscriber's inbox."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._inbox: queue.SimpleQueue[Event | None] = queue.SimpleQueue()

    def get(self, timeout: float) -> Event | None:
        """The next event; None if nothing came in `timeout` seconds. Raises EOFError once the bus is closed."""
        try:
            event = self._inbox.get(timeout=timeout)
        except queue.Empty:
            return None
        if event is None:
            raise EOFError
        return event

    def put(self, event: Event | None) -> None:
        self._inbox.put(event)

    def close(self) -> None:
        self._bus.unsubscribe(self)


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: set[Listener] = set()
        self._closed = False

    def subscribe(self) -> Listener:
        listener = Listener(self)
        with self._lock:
            if self._closed:
                listener.put(None)
            else:
                self._listeners.add(listener)
        return listener

    def unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.discard(listener)

    def publish(self, event: Event) -> None:
        with self._lock:
            for listener in self._listeners:
                listener.put(event)

    def close(self) -> None:
        """Tell every listener that nothing more will come; used when the app shuts down."""
        with self._lock:
            self._closed = True
            for listener in self._listeners:
                listener.put(None)
            self._listeners.clear()
