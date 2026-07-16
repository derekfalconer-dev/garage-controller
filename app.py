#!/usr/bin/env python3
"""Flask dashboard for the garage-door controller."""

from __future__ import annotations

import atexit
import logging
import os
import signal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template

import config
from garage_controller import CommandResult, GarageController


def configure_logging() -> logging.Logger:
    """Configure console and rotating-file logging."""
    project_directory = Path(__file__).resolve().parent
    log_directory = project_directory / config.LOG_DIRECTORY
    log_directory.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("garage_controller")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(threadName)s %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_directory / config.LOG_FILENAME,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


logger = configure_logging()
controller = GarageController(logger=logger)
controller.start()

app = Flask(__name__)


@app.get("/")
def index() -> str:
    """Render the dashboard shell."""
    return render_template("index.html")


@app.get("/api/status")
def api_status() -> Any:
    """Return current garage status."""
    return jsonify(
        {
            "ok": True,
            "status": controller.get_status().to_dict(),
        }
    )


@app.get("/api/events")
def api_events() -> Any:
    """Return recent garage-controller events."""
    return jsonify(
        {
            "ok": True,
            "events": controller.get_events(limit=20),
        }
    )


@app.post("/api/toggle")
def api_toggle() -> tuple[Any, int] | Any:
    """Request one momentary garage-door relay pulse."""
    result = controller.request_toggle()
    status = controller.get_status().to_dict()

    if result == CommandResult.ACCEPTED:
        return jsonify(
            {
                "ok": True,
                "message": "Garage-door command accepted.",
                "result": result.value,
                "status": status,
            }
        )

    if result == CommandResult.COOLDOWN:
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "Relay cooldown is still active.",
                    "result": result.value,
                    "status": status,
                }
            ),
            429,
        )

    return (
        jsonify(
            {
                "ok": False,
                "message": "Garage-door command failed.",
                "result": result.value,
                "status": status,
            }
        ),
        500,
    )


def shutdown_controller() -> None:
    """Close GPIO resources on normal interpreter shutdown."""
    controller.close()


atexit.register(shutdown_controller)


def handle_signal(signum: int, frame: object) -> None:
    logger.info("Received signal %s; shutting down", signum)
    shutdown_controller()
    raise SystemExit(0)


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


if __name__ == "__main__":
    logger.info(
        "Starting garage dashboard on %s:%s",
        config.WEB_HOST,
        config.WEB_PORT,
    )

    app.run(
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        debug=config.WEB_DEBUG,
        use_reloader=False,
        threaded=True,
    )
