"""Push notification support for the garage-door controller."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import requests


PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"


@dataclass(frozen=True)
class NotificationStatus:
    enabled: bool
    provider: str
    destination_configured: bool


class PushoverNotifier:
    """Send garage alerts through Pushover."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

        self._user_key = os.environ.get("PUSHOVER_USER_KEY", "").strip()
        self._app_token = os.environ.get("PUSHOVER_APP_TOKEN", "").strip()

        self._enabled = bool(self._user_key and self._app_token)

        if self._enabled:
            self._logger.info("Pushover notifications enabled")
        else:
            self._logger.warning(
                "Pushover notifications disabled because one or more "
                "environment variables are missing"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_status(self) -> NotificationStatus:
        return NotificationStatus(
            enabled=self._enabled,
            provider="Pushover",
            destination_configured=bool(self._user_key),
        )

    def send(
        self,
        message: str,
        *,
        title: str = "Garage Controller",
        priority: int = 1,
    ) -> bool:
        """Send one notification and return True if Pushover accepts it."""

        if not self._enabled:
            self._logger.warning(
                "Notification not sent because Pushover is disabled: %s",
                message,
            )
            return False

        try:
            response = requests.post(
                PUSHOVER_API_URL,
                data={
                    "token": self._app_token,
                    "user": self._user_key,
                    "title": title,
                    "message": message,
                    "priority": priority,
                },
                timeout=10,
            )
        except requests.RequestException:
            self._logger.exception("Pushover request failed")
            return False

        try:
            response_data = response.json()
        except ValueError:
            self._logger.error(
                "Pushover returned invalid JSON: HTTP %s body=%r",
                response.status_code,
                response.text[:500],
            )
            return False

        if response.status_code != 200 or response_data.get("status") != 1:
            self._logger.error(
                "Pushover rejected notification: HTTP %s response=%s",
                response.status_code,
                response_data,
            )
            return False

        self._logger.info(
            "Notification accepted by Pushover; request=%s",
            response_data.get("request", "unknown"),
        )
        return True


# Preserve compatibility with existing code that imports SMSNotifier.
SMSNotifier = PushoverNotifier
