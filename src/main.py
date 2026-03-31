"""Main orchestrator for IRIS Security Agent."""

import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout

from src.config import get_settings, Settings
from src.vision.camera import Camera, save_frame
from src.vision.motion_detector import MotionDetector
from src.intelligence.analyzer import SecurityAnalyzer
from src.memory.event_store import EventStore
from src.alerts.telegram_notifier import TelegramNotifier
from src.cli.interface import app as cli_app

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("data/iris.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

console = Console()
app = typer.Typer(help="IRIS Security Vision Agent")

# Global flag for graceful shutdown
running = True


def signal_handler(sig, frame):
    """Handle interrupt signals for graceful shutdown."""
    global running
    console.print("\n[yellow]Shutting down IRIS...[/yellow]")
    running = False


class IRISAgent:
    """Main IRIS Security Agent orchestrator."""

    def __init__(self, settings: Settings):
        """
        Initialize IRIS agent.

        Args:
            settings: Application settings
        """
        self.settings = settings

        # Initialize components
        self.camera = Camera(settings.camera)
        self.motion_detector = MotionDetector(settings.monitoring)
        self.event_store = EventStore(settings.storage)

        # Initialize analyzer
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

        self.analyzer = SecurityAnalyzer(settings.intelligence, settings.openai_api_key)

        # Initialize alerts if configured
        self.notifier: Optional[TelegramNotifier] = None
        if settings.alerts.enabled and settings.alerts.telegram.enabled:
            if not settings.telegram_bot_token or not settings.telegram_chat_id:
                logger.warning("Telegram credentials not set, alerts disabled")
            else:
                self.notifier = TelegramNotifier(
                    settings.alerts.telegram,
                    settings.telegram_bot_token,
                    settings.telegram_chat_id,
                )

        # State
        self.last_analysis_time: Optional[float] = None
        self.event_count = 0
        self.motion_count = 0

        # Ensure directories exist
        Path(settings.storage.snapshots_dir).mkdir(parents=True, exist_ok=True)

    def run(self, show_video: bool = False):
        """
        Run the main monitoring loop.

        Args:
            show_video: Whether to display video feed
        """
        global running

        logger.info("Starting IRIS Security Agent")
        console.print("\n[bold cyan]🔍 IRIS Security Agent Starting[/bold cyan]\n")

        # Open camera
        if not self.camera.open():
            console.print("[red]Failed to open camera. Exiting.[/red]")
            return

        console.print("[green]✓ Camera initialized[/green]")
        console.print("[green]✓ Motion detector ready[/green]")
        console.print("[green]✓ Intelligence system online[/green]")

        if self.notifier:
            console.print("[green]✓ Telegram alerts enabled[/green]")

        console.print(f"\n[yellow]Monitoring... (Press Ctrl+C to stop)[/yellow]\n")

        try:
            while running:
                # Read frame
                success, frame = self.camera.read_frame()

                if not success or frame is None:
                    logger.warning("Failed to read frame, retrying...")
                    time.sleep(1)
                    continue

                # Detect motion
                motion_detected, motion_area, annotated_frame = (
                    self.motion_detector.detect(frame)
                )

                # Show video if requested
                if show_video:
                    cv2.imshow("IRIS Security Monitor", annotated_frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                # Process motion events
                if motion_detected:
                    self.motion_count += 1

                    # Check cooldown
                    current_time = time.time()
                    if self.last_analysis_time is not None:
                        time_since_last = current_time - self.last_analysis_time
                        if time_since_last < self.settings.monitoring.cooldown_seconds:
                            continue

                    # Analyze frame
                    console.print(
                        f"[yellow]🚨 Motion detected (area: {motion_area}px) - Analyzing...[/yellow]"
                    )

                    # Get recent events for context
                    recent_events = self.event_store.get_recent_events(
                        self.settings.intelligence.context_window
                    )

                    # Run analysis
                    event = self.analyzer.analyze_frame(frame, recent_events)

                    if event is not None:
                        # Save snapshot
                        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        snapshot_filename = (
                            f"event_{timestamp_str}_{self.event_count}.jpg"
                        )
                        snapshot_path = (
                            Path(self.settings.storage.snapshots_dir)
                            / snapshot_filename
                        )

                        if save_frame(
                            frame,
                            str(snapshot_path),
                            self.settings.storage.snapshot_quality,
                        ):
                            event.snapshot_path = str(snapshot_path)

                        # Store event
                        event_id = self.event_store.add_event(event)
                        event.event_id = event_id

                        self.event_count += 1

                        # Display result
                        threat_color = {
                            "none": "green",
                            "low": "blue",
                            "medium": "yellow",
                            "high": "red",
                        }.get(event.threat_level, "white")

                        console.print(
                            f"[{threat_color}]Event #{event_id}: "
                            f"{event.threat_level.upper()} - {event.scene_description}[/{threat_color}]"
                        )

                        # Send alert if needed
                        if self.notifier:
                            self.notifier.send_alert_sync(event)

                    self.last_analysis_time = current_time

                # Small delay to prevent excessive CPU usage
                time.sleep(0.03)  # ~30 FPS

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            console.print(f"[red]Error: {e}[/red]")

        finally:
            # Cleanup
            self.cleanup(show_video)

    def cleanup(self, close_cv2: bool = False):
        """Clean up resources."""
        console.print("\n[cyan]Cleaning up...[/cyan]")

        self.camera.close()
        self.event_store.close()

        if close_cv2:
            cv2.destroyAllWindows()

        console.print(f"[green]Session complete:[/green]")
        console.print(f"  Motion events: {self.motion_count}")
        console.print(f"  Security events: {self.event_count}")
        console.print()


@app.command()
def start(
    config: Optional[str] = typer.Option(None, help="Path to config file"),
    show_video: bool = typer.Option(False, help="Display video feed"),
):
    """Start the IRIS security monitoring agent."""
    try:
        # Setup signal handler
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Load settings
        if config:
            import os

            os.environ["CONFIG_PATH"] = config

        settings = get_settings()

        # Create and run agent
        agent = IRISAgent(settings)
        agent.run(show_video=show_video)

    except Exception as e:
        console.print(f"[red]Failed to start IRIS: {e}[/red]")
        logger.error(f"Startup error: {e}", exc_info=True)
        sys.exit(1)


@app.command()
def test_camera():
    """Test camera connection and display feed."""
    console.print("\n[cyan]Testing camera...[/cyan]\n")

    try:
        settings = get_settings()
        camera = Camera(settings.camera)

        if not camera.open():
            console.print("[red]Failed to open camera[/red]")
            return

        console.print("[green]Camera opened successfully[/green]")
        console.print(f"Resolution: {camera.get_frame_size()}")
        console.print("\n[yellow]Displaying feed... Press 'q' to quit[/yellow]\n")

        while True:
            success, frame = camera.read_frame()

            if not success:
                console.print("[red]Failed to read frame[/red]")
                break

            cv2.imshow("IRIS Camera Test", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        camera.close()
        cv2.destroyAllWindows()
        console.print("\n[green]Camera test complete[/green]\n")

    except Exception as e:
        console.print(f"[red]Camera test failed: {e}[/red]")


@app.command()
def test_alert():
    """Test Telegram alert configuration."""
    console.print("\n[cyan]Testing Telegram alerts...[/cyan]\n")

    try:
        settings = get_settings()

        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            console.print("[red]Telegram credentials not configured in .env[/red]")
            return

        notifier = TelegramNotifier(
            settings.alerts.telegram,
            settings.telegram_bot_token,
            settings.telegram_chat_id,
        )

        import asyncio

        success = asyncio.run(notifier.send_test_message())

        if success:
            console.print("[green]✓ Test message sent successfully![/green]")
            console.print(f"Check your Telegram chat: {settings.telegram_chat_id}")
        else:
            console.print("[red]Failed to send test message[/red]")

    except Exception as e:
        console.print(f"[red]Alert test failed: {e}[/red]")
        logger.error(f"Alert test error: {e}", exc_info=True)


# Add CLI commands as subcommand
app.add_typer(cli_app, name="query")


if __name__ == "__main__":
    app()
