import logging
from typing import Optional, Protocol
import requests


logger = logging.getLogger(__name__)


class Messager(Protocol):
    def send_message(self, content: str): ...


def get_preferred_messager(*, discord_webhook_url: Optional[str], **kwargs) -> Messager:
    if not discord_webhook_url:
        logger.warning("discord_webhook_url not given, Discord messages disabled")
        return NullMessager()
    return DiscordMessager(discord_webhook_url, **kwargs)


class NullMessager:
    def send_message(self, content: str):
        logger.info("NullMessager.send_message: %s", content)


class DiscordMessager:
    def __init__(
        self,
        webhook_url: str,
        username: Optional[str] = None,
    ):
        if not webhook_url:
            raise ValueError("webhook_url is required")
        self._webhook_url = webhook_url
        self._username = username

    def send_message(self, content: str):
        json_body = dict(content=content)
        if self._username:
            json_body["username"] = self._username
        response = requests.post(
            self._webhook_url,
            json=json_body,
        )
        response.raise_for_status()
