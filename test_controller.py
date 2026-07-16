#!/usr/bin/env python3
"""Interactive test for the GarageController business-logic layer."""

from __future__ import annotations

import json
import sys

from gpiozero.exc import GPIOZeroError

from garage_controller import CommandResult, GarageController


def print_status(controller: GarageController) -> None:
    status = controller.get_status()

    print()
    print(json.dumps(status.to_dict(), indent=2))
    print()


def confirm_toggle() -> bool:
    print()
    print("WARNING: This will operate the garage-door relay.")
    print("The garage door may begin moving.")
    response = input("Type TOGGLE to continue: ").strip()

    return response == "TOGGLE"


def main() -> int:
    print("Garage Controller Test")
    print("======================")
    print()

    try:
        with GarageController() as controller:
            while True:
                print("Commands:")
                print("  s  Show controller status")
                print("  t  Toggle garage-door relay")
                print("  q  Quit")

                command = input("> ").strip().lower()

                if command == "s":
                    print_status(controller)

                elif command == "t":
                    if not confirm_toggle():
                        print("Command cancelled.")
                        print()
                        continue

                    original_state = controller.refresh()
                    result = controller.request_toggle()

                    if result == CommandResult.COOLDOWN:
                        status = controller.get_status()
                        print(
                            "Command rejected: relay cooldown has "
                            f"{status.cooldown_remaining_seconds:.1f} "
                            "seconds remaining."
                        )
                        print()
                        continue

                    print("Relay command accepted.")
                    print(
                        "Watching for a reed-switch state change "
                        "for up to 5 seconds..."
                    )

                    result = controller.wait_for_state_change(
                        original_state=original_state,
                        timeout_seconds=5.0,
                    )

                    if result == CommandResult.STATE_CHANGED:
                        print(
                            "Door state changed to "
                            f"{controller.refresh().value}."
                        )
                    else:
                        print(
                            "No reed-switch state change was detected "
                            "within 5 seconds."
                        )

                    print_status(controller)

                elif command == "q":
                    print("Exiting safely.")
                    return 0

                else:
                    print("Unknown command.")
                    print()

    except GPIOZeroError as exc:
        print(f"GPIO initialization failed: {exc}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\nInterrupted. Exiting safely.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
