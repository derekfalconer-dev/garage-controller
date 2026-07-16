"""Business logic for the garage-door controller."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from gpio_controller import DoorState, GarageGPIO, RelayCooldownError


class CommandResult(str, Enum):
    ACCEPTED = "ACCEPTED"
    COOLDOWN = "COOLDOWN"
    STATE_CHANGED = "STATE_CHANGED"
    STATE_UNCHANGED = "STATE_UNCHANGED"


@dataclass(frozen=True)
class GarageStatus:
    """Snapshot of the garage-controller state."""

    door_state: str
    previous_door_state: str | None
    relay_active: bool
    command_allowed: bool
    cooldown_remaining_seconds: float
    last_transition_at: str | None
    last_command_at: str | None
    last_command_result: str | None
    seconds_in_current_state: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GarageController:
    """
    Owns garage-door state and command logic.

    The GPIO layer reads and drives hardware. This controller adds state
    tracking, cooldown enforcement, timestamps, and command-result tracking.
    """

    def __init__(self, gpio: GarageGPIO | None = None) -> None:
        self._gpio = gpio if gpio is not None else GarageGPIO()
        self._owns_gpio = gpio is None

        self._lock = threading.RLock()
        self._closed = False

        initial_state = self._gpio.get_door_state()

        self._current_state = initial_state
        self._previous_state: DoorState | None = None

        self._state_changed_monotonic = time.monotonic()
        self._last_transition_at: datetime | None = None

        self._last_command_at: datetime | None = None
        self._last_command_result: CommandResult | None = None

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
            raise RuntimeError("GarageController has already been closed.")

    def refresh(self) -> DoorState:
        """
        Read the reed switch and update tracked state when it changes.

        This method is intentionally inexpensive and can be called frequently
        by a Flask status endpoint or monitoring thread.
        """
        with self._lock:
            self._ensure_open()

            observed_state = self._gpio.get_door_state()

            if observed_state != self._current_state:
                self._previous_state = self._current_state
                self._current_state = observed_state
                self._state_changed_monotonic = time.monotonic()
                self._last_transition_at = self._utc_now()

            return self._current_state

    def get_status(self) -> GarageStatus:
        """Return a complete, immutable status snapshot."""
        with self._lock:
            self._ensure_open()
            self.refresh()

            cooldown_remaining = self._gpio.cooldown_remaining()

            return GarageStatus(
                door_state=self._current_state.value,
                previous_door_state=(
                    self._previous_state.value
                    if self._previous_state is not None
                    else None
                ),
                relay_active=self._gpio.relay_is_active(),
                command_allowed=(
                    not self._gpio.relay_is_active()
                    and cooldown_remaining <= 0
                ),
                cooldown_remaining_seconds=round(cooldown_remaining, 1),
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
            )

    def request_toggle(self) -> CommandResult:
        """
        Request one momentary relay pulse.

        The relay only simulates the existing wall-button contact. Door state
        is never inferred from the command; it remains reed-switch driven.
        """
        with self._lock:
            self._ensure_open()
            self.refresh()

            try:
                self._gpio.pulse_relay()
            except RelayCooldownError:
                self._last_command_result = CommandResult.COOLDOWN
                return CommandResult.COOLDOWN

            self._last_command_at = self._utc_now()
            self._last_command_result = CommandResult.ACCEPTED
            return CommandResult.ACCEPTED

    def wait_for_state_change(
        self,
        original_state: DoorState,
        timeout_seconds: float = 5.0,
        poll_interval_seconds: float = 0.1,
    ) -> CommandResult:
        """
        Wait briefly for the reed switch to report a changed state.

        This does not block relay operation; it is intended for tests or
        background monitoring rather than direct use in a Flask request.
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        if poll_interval_seconds <= 0:
            raise ValueError(
                "poll_interval_seconds must be greater than zero."
            )

        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            current_state = self.refresh()

            if current_state != original_state:
                with self._lock:
                    self._last_command_result = CommandResult.STATE_CHANGED

                return CommandResult.STATE_CHANGED

            time.sleep(poll_interval_seconds)

        with self._lock:
            self._last_command_result = CommandResult.STATE_UNCHANGED

        return CommandResult.STATE_UNCHANGED

    def close(self) -> None:
        """Release controller and GPIO resources safely."""
        with self._lock:
            if self._closed:
                return

            if self._owns_gpio:
                self._gpio.cleanup()

            self._closed = True

    def __enter__(self) -> GarageController:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
