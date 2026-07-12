from __future__ import annotations

from threading import Lock

from .events import DomainEvent


class DomainEventPublisher:
    def __init__(self) -> None:
        self._events: list[DomainEvent] = []
        self._lock = Lock()

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            self._events.append(event)

    def publish_all(self, events: list[DomainEvent]) -> None:
        with self._lock:
            self._events.extend(events)

    def list_events(self) -> list[DomainEvent]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


domain_event_publisher = DomainEventPublisher()


def publish_domain_events(events: list[DomainEvent]) -> None:
    domain_event_publisher.publish_all(events)


def get_published_events() -> list[DomainEvent]:
    return domain_event_publisher.list_events()


def clear_published_events() -> None:
    domain_event_publisher.clear()
