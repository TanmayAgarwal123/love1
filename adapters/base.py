"""Clean adapter interfaces. Swap an implementation without touching workflows."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Message:
    id: str
    ts: datetime
    sender: str          # "me", "partner", or the raw name for anyone else
    text: str
    source: str = ""


@dataclass
class Event:
    uid: str
    summary: str
    start: datetime
    end: datetime
    all_day: bool = False
    whose: str = "mine"  # "mine" | "hers"
    calendar: str = ""
    attendees: tuple = field(default_factory=tuple)
    description: str = ""
    location: str = ""
    work: bool = False
    transparent: bool = False

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


class MessageSource(ABC):
    """Read-only access to the conversation. There is deliberately no write method."""

    @abstractmethod
    def messages(self) -> list[Message]: ...

    def drafts(self) -> list[Message]:
        return []


class CalendarSource(ABC):
    """Read-only access to calendars."""

    @abstractmethod
    def events(self, start: datetime, end: datetime, whose: str | None = None) -> list[Event]: ...


class Notifier(ABC):
    """Nudges for YOU. Takes no recipient: it cannot address anyone else."""

    @abstractmethod
    def notify(self, title: str, body: str) -> None: ...


class NullMessageSource(MessageSource):
    def messages(self) -> list[Message]:
        return []


class NullCalendarSource(CalendarSource):
    def events(self, start, end, whose=None) -> list[Event]:
        return []
