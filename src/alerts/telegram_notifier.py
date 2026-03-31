"""Telegram notification module for IRIS Security Agent."""

import logging
from pathlib import Path
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

from src.config import TelegramConfig
from src.memory.event_store import SecurityEvent

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends security alerts via Telegram."""

    # Emoji mapping for threat levels
    THREAT_EMOJI = {"none": "✅", "low": "ℹ️", "medium": "⚠️", "high": "🚨"}

    # Minimum threat levels (ordered)
    THREAT_LEVELS = ["none", "low", "medium", "high"]

    def __init__(self, config: TelegramConfig, bot_token: str, chat_id: str):
        """
        Initialize Telegram notifier.

        Args:
            config: Telegram configuration
            bot_token: Telegram bot token
            chat_id: Target chat ID
        """
        self.config = config
        self.bot_token = bot_token
        self.chat_id = chat_id

        try:
            self.bot = Bot(token=bot_token)
            logger.info("Telegram bot initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self.bot = None

    async def send_alert(self, event: SecurityEvent) -> bool:
        """
        Send security alert to Telegram.

        Args:
            event: SecurityEvent to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.config.enabled:
            logger.debug("Telegram alerts disabled")
            return False

        if self.bot is None:
            logger.error("Telegram bot not initialized")
            return False

        # Check if event meets minimum threat level
        if not self._should_alert(event.threat_level):
            logger.debug(f"Event threat level '{event.threat_level}' below threshold")
            return False

        try:
            # Format message
            message = self._format_message(event)

            # Send message
            if self.config.include_snapshot and event.snapshot_path:
                # Send photo with caption
                snapshot_path = Path(event.snapshot_path)

                if snapshot_path.exists():
                    with open(snapshot_path, "rb") as photo:
                        await self.bot.send_photo(
                            chat_id=self.chat_id,
                            photo=photo,
                            caption=message,
                            parse_mode="HTML",
                        )
                else:
                    logger.warning(
                        f"Snapshot not found: {snapshot_path}, sending text only"
                    )
                    await self.bot.send_message(
                        chat_id=self.chat_id, text=message, parse_mode="HTML"
                    )
            else:
                # Send text only
                await self.bot.send_message(
                    chat_id=self.chat_id, text=message, parse_mode="HTML"
                )

            logger.info(f"Alert sent for event #{event.event_id}")
            return True

        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending alert: {e}", exc_info=True)
            return False

    def send_alert_sync(self, event: SecurityEvent) -> bool:
        """
        Synchronous wrapper for send_alert.

        Args:
            event: SecurityEvent to send

        Returns:
            True if sent successfully, False otherwise
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.send_alert(event))

    async def send_test_message(self) -> bool:
        """
        Send a test message to verify bot configuration.

        Returns:
            True if successful, False otherwise
        """
        if self.bot is None:
            logger.error("Telegram bot not initialized")
            return False

        try:
            message = (
                "🤖 <b>IRIS Security Agent - Test Message</b>\n\n"
                "If you can see this, alerts are configured correctly!\n\n"
                f"Chat ID: <code>{self.chat_id}</code>"
            )

            await self.bot.send_message(
                chat_id=self.chat_id, text=message, parse_mode="HTML"
            )

            logger.info("Test message sent successfully")
            return True

        except TelegramError as e:
            logger.error(f"Failed to send test message: {e}")
            return False

    def _should_alert(self, threat_level: str) -> bool:
        """
        Check if threat level meets minimum threshold.

        Args:
            threat_level: Event threat level

        Returns:
            True if should alert, False otherwise
        """
        try:
            event_level_idx = self.THREAT_LEVELS.index(threat_level)
            min_level_idx = self.THREAT_LEVELS.index(self.config.alert_on_threat_level)
            return event_level_idx >= min_level_idx
        except ValueError:
            logger.warning(f"Unknown threat level: {threat_level}")
            return False

    def _format_message(self, event: SecurityEvent) -> str:
        """
        Format security event as Telegram message.

        Args:
            event: SecurityEvent to format

        Returns:
            Formatted HTML message
        """
        emoji = self.THREAT_EMOJI.get(event.threat_level, "❓")

        # Threat level formatting
        threat_display = event.threat_level.upper()
        if event.threat_level == "high":
            threat_display = f"<b>{threat_display}</b>"

        # Time formatting
        time_str = event.timestamp.strftime("%Y-%m-%d %H:%M:%S")

        message = f"""{emoji} <b>IRIS Security Alert</b>

<b>Threat Level:</b> {threat_display}
<b>Time:</b> {time_str}

<b>Scene:</b> {event.scene_description}
<b>People Detected:</b> {event.people_count}
<b>Activity:</b> {event.activity.capitalize()}

<b>Analysis:</b>
{event.reasoning}
"""

        if event.event_id:
            message += f"\n<i>Event ID: #{event.event_id}</i>"

        return message


def create_notifier(
    bot_token: str, chat_id: str, config: Optional[TelegramConfig] = None
) -> TelegramNotifier:
    """
    Factory function to create TelegramNotifier.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        config: Optional TelegramConfig

    Returns:
        Configured TelegramNotifier
    """
    if config is None:
        config = TelegramConfig()

    return TelegramNotifier(config, bot_token, chat_id)
