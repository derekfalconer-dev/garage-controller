"""GPIO hardware abstraction for the garage-door controller."""

from __future__ import annotations

import threading
import time
from enum import Enum

from gpiozero import Button, OutputDevice

import config


class DoorState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class RelayCooldownError(RuntimeError):
    """Raised when a relay pulse is requested during the cooldown period."""


class GarageGPIO:
    """Owns all access to the garage-door GPIO hardware."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_relay_pulse_monotonic: float | None = None

        # GPIO17 uses an internal pull-up:
        # switch closed to ground -> LOW -> is_pressed = True
        self._reed_switch = Button(
            pin=config.REED_GPIO,
            pull_up=True,
            bounce_time=config.REED_BOUNCE_SECONDS,
        )

        # For an active-low relay:
        # active_high=False means on() drives LOW and off() drives HIGH.
        #
        # initial_value=False guarantees the relay begins released.
        self._relay = OutputDevice(
            pin=config.RELAY_GPIO,
            active_high=config.RELAY_ACTIVE_HIGH,
            initial_value=False,
        )

        # Explicitly force the safe state.
        self._relay.off()

    def get_door_state(self) -> DoorState:
        """Return the current door state from the reed switch."""
        if self._reed_switch.is_pressed:
            return DoorState.CLOSED

        return DoorState.OPEN

    def relay_is_active(self) -> bool:
        """Return True while the relay output is energized."""
        return self._relay.is_active

    def cooldown_remaining(self) -> float:
        """Return remaining relay cooldown time in seconds."""
        if self._last_relay_pulse_monotonic is None:
            return 0.0

        elapsed = time.monotonic() - self._last_relay_pulse_monotonic
        remaining = config.RELAY_COOLDOWN_SECONDS - elapsed
        return max(0.0, remaining)

    def pulse_relay(self, force: bool = False) -> None:
        """
        Energize the relay briefly, then guarantee it is released.

        Set force=True only for deliberate hardware testing.
        """
        with self._lock:
            remaining = self.cooldown_remaining()

            if remaining > 0 and not force:
                raise RelayCooldownError(
                    f"Relay cooldown active for another {remaining:.1f} seconds."
                )

            try:
                self._relay.on()
                time.sleep(config.RELAY_PULSE_SECONDS)
            finally:
                # The relay must always return to its safe, released state.
                self._relay.off()
                self._last_relay_pulse_monotonic = time.monotonic()

    def cleanup(self) -> None:
        """Release GPIO resources safely."""
        try:
            self._relay.off()
        finally:
            self._relay.close()
            self._reed_switch.close()

    def __enter__(self) -> GarageGPIO:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.cleanup()
