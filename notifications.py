"""SMS notification support for the garage-door controller."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from twilio.rest import Client


@dataclass(frozen=True)
class NotificationStatus:
    enabled: bool
    provider: str
    destination_configured: bool


class SMSNotifier:
    """Send SMS alerts using credentials supplied through the environment."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

        self._account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        self._auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        self._from_number = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
        self._to_number = os.environ.get("GARAGE_SMS_TO", "").strip()

        self._enabled = all(
            (
                self._account_sid,
                self._auth_token,
                self._from_number,
                self._to_number,
            )
        )

        self._client: Client | None = None

        if self._enabled:
            self._client = Client(
                username=self._account_sid,
                password=self._auth_token,
            )
            self._logger.info("Twilio SMS notifications enabled")
        else:
            self._logger.warning(
                "SMS notifications disabled because one or more "
                "environment variables are missing"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_status(self) -> NotificationStatus:
        return NotificationStatus(
            enabled=self._enabled,
            provider="Twilio",
            destination_configured=bool(self._to_number),
        )

    def send(self, message: str) -> bool:
        """Send one SMS message. Return True only if Twilio accepts it."""
        if not self._enabled or self._client is None:
            self._logger.warning(
                "SMS not sent because notifications are disabled: %s",
                message,
            )
            return False

        try:
            result = self._client.messages.create(
                body=message,
                from_=self._from_number,
                to=self._to_number,
            )
        except Exception:
            self._logger.exception("SMS send failed")
            return False

        self._logger.info("SMS accepted by Twilio; SID=%s", result.sid)
        return True
