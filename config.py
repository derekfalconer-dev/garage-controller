"""Configuration for the garage-door controller."""

# GPIO numbering uses BCM numbers, not physical header pin numbers.
REED_GPIO = 17       # Physical pin 11
RELAY_GPIO = 23      # Physical pin 16

# Reed switch wiring:
# GPIO17 ---- reed switch ---- GND
#
# Internal pull-up is enabled, therefore:
# LOW  = magnet present / door closed
# HIGH = magnet absent / door open
REED_ACTIVE_STATE = False

# Relay module wiring:
# 3.3V ---- DC+
# GND  ---- DC-
# GPIO23 ---- IN
#
# The opto-isolated relay board is expected to be active-low:
# LOW  = relay energized
# HIGH = relay released
RELAY_ACTIVE_HIGH = False

# Garage openers generally need only a brief momentary contact.
RELAY_PULSE_SECONDS = 0.5

# Prevent accidental repeated commands.
RELAY_COOLDOWN_SECONDS = 5.0

# Reed-switch debounce time.
REED_BOUNCE_SECONDS = 0.05
