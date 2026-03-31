"""CLI interface for IRIS Security Agent."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from src.config import get_settings
from src.memory.event_store import EventStore

app = typer.Typer(help="IRIS Security Agent CLI")
console = Console()
logger = logging.getLogger(__name__)


def format_threat_level(threat_level: str) -> str:
    """Format threat level with color."""
    colors = {"none": "green", "low": "blue", "medium": "yellow", "high": "red"}
    color = colors.get(threat_level, "white")
    return f"[{color}]{threat_level.upper()}[/{color}]"


def format_activity(activity: str) -> str:
    """Format activity with color."""
    colors = {"normal": "green", "suspicious": "yellow", "alert": "red"}
    color = colors.get(activity, "white")
    return f"[{color}]{activity.capitalize()}[/{color}]"


@app.command()
def query(
    last: Optional[str] = typer.Option(
        None, help="Time range (e.g., '24h', '7d', '2w')"
    ),
    threat: Optional[str] = typer.Option(
        None, help="Filter by threat level (none/low/medium/high)"
    ),
    limit: int = typer.Option(10, help="Maximum number of events to show"),
    today: bool = typer.Option(False, help="Show only today's events"),
):
    """Query security events from the database."""
    try:
        settings = get_settings()
        store = EventStore(settings.storage)

        # Determine which events to fetch
        if today:
            events = store.get_events_today()
            console.print("\n[bold cyan]Today's Security Events[/bold cyan]\n")
        elif threat:
            events = store.get_events_by_threat_level(threat, limit)
            console.print(
                f"\n[bold cyan]Events with {format_threat_level(threat)} threat level[/bold cyan]\n"
            )
        elif last:
            # Parse time range
            start_time = parse_time_range(last)
            if start_time:
                end_time = datetime.now()
                events = store.get_events_by_timerange(start_time, end_time)
                console.print(f"\n[bold cyan]Events from last {last}[/bold cyan]\n")
            else:
                console.print(
                    "[red]Invalid time range format. Use format like '24h', '7d', '2w'[/red]"
                )
                return
        else:
            events = store.get_recent_events(limit)
            console.print(
                f"\n[bold cyan]Recent Security Events (last {limit})[/bold cyan]\n"
            )

        if not events:
            console.print("[yellow]No events found[/yellow]")
            return

        # Create table
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=6)
        table.add_column("Time", style="cyan", width=19)
        table.add_column("Threat", width=10)
        table.add_column("Activity", width=12)
        table.add_column("People", justify="center", width=7)
        table.add_column("Scene", style="white")

        for event in events:
            table.add_row(
                f"#{event.event_id}",
                event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                format_threat_level(event.threat_level),
                format_activity(event.activity),
                str(event.people_count),
                event.scene_description[:50] + "..."
                if len(event.scene_description) > 50
                else event.scene_description,
            )

        console.print(table)
        console.print(f"\n[dim]Total events: {len(events)}[/dim]\n")

        store.close()

    except Exception as e:
        console.print(f"[red]Error querying events: {e}[/red]")
        logger.error(f"Query error: {e}", exc_info=True)


@app.command()
def show(event_id: int):
    """Show detailed information about a specific event."""
    try:
        settings = get_settings()
        store = EventStore(settings.storage)

        event = store.get_event(event_id)

        if event is None:
            console.print(f"[red]Event #{event_id} not found[/red]")
            return

        # Create detailed panel
        content = f"""[bold]Time:[/bold] {event.timestamp.strftime("%Y-%m-%d %H:%M:%S")}
[bold]Threat Level:[/bold] {format_threat_level(event.threat_level)}
[bold]Activity:[/bold] {format_activity(event.activity)}
[bold]People Count:[/bold] {event.people_count}

[bold]Scene Description:[/bold]
{event.scene_description}

[bold]Reasoning:[/bold]
{event.reasoning}
"""

        if event.snapshot_path:
            content += f"\n[bold]Snapshot:[/bold] {event.snapshot_path}"

        if event.metadata:
            content += f"\n\n[bold]Metadata:[/bold]\n"
            for key, value in event.metadata.items():
                content += f"  {key}: {value}\n"

        panel = Panel(
            content,
            title=f"[bold cyan]Event #{event_id}[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )

        console.print("\n")
        console.print(panel)
        console.print("\n")

        store.close()

    except Exception as e:
        console.print(f"[red]Error showing event: {e}[/red]")
        logger.error(f"Show error: {e}", exc_info=True)


@app.command()
def stats():
    """Show statistics about stored events."""
    try:
        settings = get_settings()
        store = EventStore(settings.storage)

        statistics = store.get_statistics()

        content = f"""[bold]Total Events:[/bold] {statistics["total_events"]}
[bold]Events Today:[/bold] {statistics["events_today"]}
[bold]Average People Count:[/bold] {statistics["average_people_count"]}

[bold]Threat Level Distribution:[/bold]"""

        for level in ["none", "low", "medium", "high"]:
            count = statistics["threat_level_distribution"].get(level, 0)
            bar = "█" * (count // 5) if count > 0 else ""
            content += f"\n  {format_threat_level(level):20} {count:4} {bar}"

        panel = Panel(
            content,
            title="[bold cyan]IRIS Statistics[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )

        console.print("\n")
        console.print(panel)
        console.print("\n")

        store.close()

    except Exception as e:
        console.print(f"[red]Error showing statistics: {e}[/red]")
        logger.error(f"Stats error: {e}", exc_info=True)


def parse_time_range(time_str: str) -> Optional[datetime]:
    """
    Parse time range string to datetime.

    Args:
        time_str: Time range string (e.g., '24h', '7d', '2w')

    Returns:
        Start datetime or None if invalid
    """
    try:
        amount = int(time_str[:-1])
        unit = time_str[-1].lower()

        if unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        elif unit == "w":
            delta = timedelta(weeks=amount)
        else:
            return None

        return datetime.now() - delta

    except (ValueError, IndexError):
        return None


if __name__ == "__main__":
    app()
