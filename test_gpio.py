#!/usr/bin/env python3
"""Interactive hardware test for the garage-door controller."""

from __future__ import annotations

import sys
import time

from gpiozero.exc import GPIOZeroError

import config
from gpio_controller import GarageGPIO, RelayCooldownError


def print_status(gpio: GarageGPIO) -> None:
    """Print the current GPIO state."""
    door_state = gpio.get_door_state().value
    relay_state = "ACTIVE" if gpio.relay_is_active() else "OFF"
    cooldown = gpio.cooldown_remaining()

    print()
    print(f"Door state:       {door_state}")
    print(f"Relay state:      {relay_state}")
    print(f"Cooldown left:    {cooldown:.1f} seconds")
    print()


def watch_switch(gpio: GarageGPIO) -> None:
    """Continuously display reed-switch changes until Ctrl+C."""
    print()
    print("Watching reed switch. Press Ctrl+C to stop.")
    print(f"Initial state: {gpio.get_door_state().value}")

    previous_state = gpio.get_door_state()

    try:
        while True:
            current_state = gpio.get_door_state()

            if current_state != previous_state:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"{timestamp}  Door state changed to {current_state.value}")
                previous_state = current_state

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopped watching reed switch.")


def confirm_relay_pulse() -> bool:
    """Require explicit confirmation before energizing the relay."""
    print()
    print("WARNING: This will pulse the garage-door relay.")
    print("If connected to the opener, the door may move.")
    response = input("Type PULSE to continue: ").strip()

    return response == "PULSE"


def main() -> int:
    print("Garage GPIO Hardware Test")
    print("=========================")
    print(f"Reed switch: BCM GPIO {config.REED_GPIO}, physical pin 11")
    print(f"Relay input: BCM GPIO {config.RELAY_GPIO}, physical pin 16")
    print()

    try:
        with GarageGPIO() as gpio:
            while True:
                print("Commands:")
                print("  s  Show current status")
                print("  w  Watch reed-switch changes")
                print("  p  Pulse relay")
                print("  q  Quit")

                command = input("> ").strip().lower()

                if command == "s":
                    print_status(gpio)

                elif command == "w":
                    watch_switch(gpio)

                elif command == "p":
                    if not confirm_relay_pulse():
                        print("Relay pulse cancelled.")
                        continue

                    try:
                        print(
                            f"Pulsing relay for "
                            f"{config.RELAY_PULSE_SECONDS:.2f} seconds..."
                        )
                        gpio.pulse_relay()
                        print("Relay pulse complete. Relay is OFF.")

                    except RelayCooldownError as exc:
                        print(exc)

                elif command == "q":
                    print("Exiting. Relay is OFF.")
                    return 0

                else:
                    print("Unknown command.")

                print()

    except GPIOZeroError as exc:
        print(f"GPIO initialization failed: {exc}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\nInterrupted. Cleaning up GPIO.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
