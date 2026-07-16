"""Continuous business logic for the garage-door controller."""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import config
from gpio_controller import DoorState, GarageGPIO, RelayCooldownError
from notifications import SMSNotifier


class CommandResult(str, Enum):
    ACCEPTED = "ACCEPTED"
    COOLDOWN = "COOLDOWN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class GarageEvent:
    timestamp: str
    event_type: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class GarageStatus:
    hostname: str
    door_state: str
    previous_door_state: str | None
    relay_active: bool
    command_allowed: bool
    cooldown_remaining_seconds: float
    last_transition_at: str | None
    last_command_at: str | None
    last_command_result: str | None
    seconds_in_current_state: float
    monitor_running: bool
    sms_enabled: bool
    open_alert_seconds: int
    open_alert_sent: bool
    open_alert_due_in_seconds: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GarageController:
    """Own GPIO state, monitoring, events, relay commands, and alerts."""

    def __init__(
        self,
        gpio: GarageGPIO | None = None,
        notifier: SMSNotifier | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._gpio = gpio if gpio is not None else GarageGPIO()
        self._owns_gpio = gpio is None
        self._logger = logger or logging.getLogger(__name__)
        self._notifier = notifier or SMSNotifier(logger=self._logger)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._closed = False
        self._hostname = socket.gethostname()

        initial_state = self._gpio.get_door_state()

        self._current_state = initial_state
        self._previous_state: DoorState | None = None
        self._state_changed_monotonic = time.monotonic()
        self._last_transition_at = self._utc_now()

        self._last_command_at: datetime | None = None
        self._last_command_result: CommandResult | None = None

        self._open_started_monotonic: float | None = (
            time.monotonic()
            if initial_state == DoorState.OPEN
            else None
        )
        self._open_alert_sent = False

        self._events: deque[GarageEvent] = deque(
            maxlen=config.EVENT_HISTORY_LIMIT
        )

        self._record_event(
            "SYSTEM_START",
            f"Controller started; door is {initial_state.value}",
        )

        if not self._notifier.enabled:
            self._record_event(
                "SMS_DISABLED",
                "SMS alerts are not configured",
            )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat(timespec="seconds")

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("GarageController has been closed.")

    def _record_event(self, event_type: str, message: str) -> None:
        event = GarageEvent(
            timestamp=self._utc_now().isoformat(timespec="seconds"),
            event_type=event_type,
            message=message,
        )
        self._events.appendleft(event)
        self._logger.info("%s: %s", event_type, message)

    def start(self) -> None:
        with self._lock:
            self._ensure_open()

            if self.monitor_running:
                return

            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="garage-monitor",
                daemon=True,
            )
            self._monitor_thread.start()
            self._record_event(
                "MONITOR_START",
                "Background monitor started",
            )

    @property
    def monitor_running(self) -> bool:
        thread = self._monitor_thread
        return thread is not None and thread.is_alive()

    def _monitor_loop(self) -> None:
        while not self._stop_event.wait(config.MONITOR_INTERVAL_SECONDS):
            try:
                self.refresh()
                self._check_open_alert()
            except Exception:
                self._logger.exception("Unexpected garage monitor error")

        self._logger.info("Garage monitor thread stopped")

    def refresh(self) -> DoorState:
        with self._lock:
            self._ensure_open()

            observed_state = self._gpio.get_door_state()

            if observed_state == self._current_state:
                return self._current_state

            old_state = self._current_state
            self._previous_state = old_state
            self._current_state = observed_state
            self._state_changed_monotonic = time.monotonic()
            self._last_transition_at = self._utc_now()

            if observed_state == DoorState.OPEN:
                self._open_started_monotonic = time.monotonic()
                self._open_alert_sent = False
                self._record_event(
                    "DOOR_OPENED",
                    "Garage door opened",
                )
            else:
                self._open_started_monotonic = None
                self._open_alert_sent = False
                self._record_event(
                    "DOOR_CLOSED",
                    "Garage door closed",
                )

            self._logger.info(
                "Door state changed: %s -> %s",
                old_state.value,
                observed_state.value,
            )

            return self._current_state

    def _check_open_alert(self) -> None:
        with self._lock:
            if self._current_state != DoorState.OPEN:
                return

            if self._open_started_monotonic is None:
                self._open_started_monotonic = time.monotonic()
                return

            if self._open_alert_sent:
                return

            open_seconds = (
                time.monotonic() - self._open_started_monotonic
            )

            if open_seconds < config.OPEN_ALERT_SECONDS:
                return

            message = (
                f"Garage alert from {self._hostname}: "
                f"the garage door has been open for "
                f"{int(open_seconds // 60)} minutes."
            )

            sent = self._notifier.send(message)

            if sent:
                self._open_alert_sent = True
                self._record_event(
                    "SMS_SENT",
                    "Open-door SMS alert sent",
                )
            else:
                # Mark it sent for this open cycle even when SMS is disabled
                # or fails. This prevents retrying every 0.1 seconds.
                self._open_alert_sent = True
                self._record_event(
                    "SMS_FAILED",
                    "Open-door SMS alert could not be sent",
                )

    def get_events(self, limit: int = 20) -> list[dict[str, str]]:
        with self._lock:
            safe_limit = max(1, min(limit, config.EVENT_HISTORY_LIMIT))
            return [
                event.to_dict()
                for event in list(self._events)[:safe_limit]
            ]

    def get_status(self) -> GarageStatus:
        with self._lock:
            self._ensure_open()
            self.refresh()

            cooldown_remaining = self._gpio.cooldown_remaining()
            relay_active = self._gpio.relay_is_active()

            alert_due: float | None = None

            if (
                self._current_state == DoorState.OPEN
                and self._open_started_monotonic is not None
                and not self._open_alert_sent
            ):
                elapsed = (
                    time.monotonic() - self._open_started_monotonic
                )
                alert_due = max(
                    0.0,
                    config.OPEN_ALERT_SECONDS - elapsed,
                )

            return GarageStatus(
                hostname=self._hostname,
                door_state=self._current_state.value,
                previous_door_state=(
                    self._previous_state.value
                    if self._previous_state is not None
                    else None
                ),
                relay_active=relay_active,
                command_allowed=(
                    not relay_active and cooldown_remaining <= 0
                ),
                cooldown_remaining_seconds=round(
                    cooldown_remaining,
                    1,
                ),
                last_transition_at=self._format_datetime(
                    self._last_transition_at
                ),
                last_command_at=self._format_datetime(
                    self._last_command_at
                ),
                last_command_result=(
                    self._last_command_result.value
                    if self._last_command_result is not None
                    else None
                ),
                seconds_in_current_state=round(
                    time.monotonic() - self._state_changed_monotonic,
                    1,
                ),
                monitor_running=self.monitor_running,
                sms_enabled=self._notifier.enabled,
                open_alert_seconds=config.OPEN_ALERT_SECONDS,
                open_alert_sent=self._open_alert_sent,
                open_alert_due_in_seconds=(
                    round(alert_due, 1)
                    if alert_due is not None
                    else None
                ),
            )

    def request_toggle(self) -> CommandResult:
        with self._lock:
            self._ensure_open()

            try:
                self._gpio.pulse_relay()
            except RelayCooldownError:
                self._last_command_result = CommandResult.COOLDOWN
                self._record_event(
                    "COMMAND_REJECTED",
                    "Relay command rejected during cooldown",
                )
                return CommandResult.COOLDOWN
            except Exception:
                self._last_command_result = CommandResult.ERROR
                self._logger.exception("Relay command failed")
                self._record_event(
                    "COMMAND_ERROR",
                    "Relay command failed",
                )
                return CommandResult.ERROR

            self._last_command_at = self._utc_now()
            self._last_command_result = CommandResult.ACCEPTED
            self._record_event(
                "RELAY_PULSE",
                "Garage-door relay pulsed",
            )

            return CommandResult.ACCEPTED

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return

            self._stop_event.set()
            monitor_thread = self._monitor_thread

        if (
            monitor_thread is not None
            and monitor_thread.is_alive()
            and monitor_thread is not threading.current_thread()
        ):
            monitor_thread.join(timeout=2.0)

        with self._lock:
            if self._owns_gpio:
                self._gpio.cleanup()

            self._closed = True
            self._logger.info("Garage controller closed")

    def __enter__(self) -> GarageController:
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
