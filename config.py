"""Configuration for the garage-door controller."""

# GPIO numbering uses BCM numbers.
REED_GPIO = 17
RELAY_GPIO = 23

REED_BOUNCE_SECONDS = 0.05
RELAY_ACTIVE_HIGH = False
RELAY_PULSE_SECONDS = 0.5
RELAY_COOLDOWN_SECONDS = 5.0

# Background monitoring.
MONITOR_INTERVAL_SECONDS = 0.10

# Alert after the door remains open this long.
OPEN_ALERT_SECONDS = 10 * 60

# Maximum number of recent events retained in memory.
EVENT_HISTORY_LIMIT = 50

# Web server.
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000
WEB_DEBUG = False

# Logging.
LOG_DIRECTORY = "logs"
LOG_FILENAME = "garage-controller.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5
