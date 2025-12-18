import os
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.columns import Columns
from rich.align import Align

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# --- Project Imports ---
# Add the root directory to the path to import from 'src'
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from src.models import Trade, StatusLog
    from src.config import settings
except ImportError as e:
    console = Console() # Initialize console for error output
    console.print(f"[bold red]Error: Could not import necessary modules: {e}[/bold red]")
    console.print("Ensure the project structure is correct and you are in the root directory.")
    sys.exit(1)

# --- Database Configuration for the monitor ---
# The monitor uses settings.postgres_host.
# If running in Docker Compose, POSTGRES_HOST will be 'db'.
# If running on the host (and .env indicates so), POSTGRES_HOST will be 'localhost'.
MONITOR_DB_URL = (
    f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)

console = Console()
try:
    engine = create_engine(MONITOR_DB_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Test the connection
    with engine.connect() as connection:
        pass
    console.print("[green]Database connection successfully established.[/green]")
except Exception as e:
    console.print(f"[bold red]Error connecting to the database: {e}[/bold red]")
    console.print("Please check the following:")
    console.print("1. Is PostgreSQL running on your local machine or the 'db' service in Docker Compose?")
    console.print("2. Is port 5432 available and accessible?")
    console.print("3. Does your .env file have the correct credentials (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB)?")
    console.print("4. If you are in Docker Compose, is the 'db' service up and healthy?")
    sys.exit(1)


def make_layout() -> Layout:
    """Defines the layout structure for the monitor."""
    layout = Layout(name="root")

    layout.split_column(  # Split root vertically first
        Layout(name="header", size=3),
        Layout(name="main_content")
    )
    layout["main_content"].split_row(  # Then split main_content horizontally
        Layout(name="left_pane", ratio=1),
        Layout(name="right_pane", ratio=2),
    )
    return layout

def make_status_table(status_data: dict | None) -> Panel:
    """Creates the table for the left panel (live status)."""
    table = Table(
        title="[bold underline]Current Strategy Status[/bold underline]",
        show_header=True, 
        header_style="bold magenta", 
        border_style="cyan"
    )
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", justify="left", style="green")

    if not status_data:
        table.add_row("Info", "[yellow]Waiting for strategy data...[/yellow]")
    else:
        table.add_row("Timestamp", status_data['timestamp'])
        table.add_row("Strategy", status_data['strategy'])
        
        signal = status_data['signal']
        signal_display = ""
        if signal == "BUY":
            signal_display = f"[bold green]▲ BUY[/bold green]"
        elif signal == "SELL":
            signal_display = f"[bold red]▼ SELL[/bold red]"
        else: # HOLD
            signal_display = f"[bold blue]▬ HOLD[/bold blue]"
        table.add_row("Signal", signal_display)
        
        table.add_row("Close Price", f"{status_data['close_price']:.4f}")
        table.add_row("RSI", f"{status_data['rsi']:.2f}" if status_data['rsi'] is not None else "N/A")
        table.add_row("USDT Balance", f"{status_data['balance_usdt']:.2f}" if status_data['balance_usdt'] is not None else "N/A")
    
    return Panel(Align.center(table), title="[bold white]Strategy Monitor[/bold white]", border_style="bright_blue")


def make_trades_table(trades_data: list[dict]) -> Panel:
    """Creates the table for the right panel (trade history)."""
    table = Table(
        show_header=True, 
        header_style="bold green", 
        border_style="yellow"
    )
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Timestamp", style="cyan", no_wrap=True)
    table.add_column("Symbol", style="magenta")
    table.add_column("Decision", justify="center")
    table.add_column("Price", justify="right")
    table.add_column("Quantity", justify="right")

    if not trades_data:
        table.add_row("", "[yellow]No trades registered yet.[/yellow]", "", "", "", "")
    else:
        for trade in trades_data:
            decision_color = "green" if trade['decision'] == "BUY" else "red"
            table.add_row(
                str(trade['id']),
                trade['timestamp'],
                trade['symbol'],
                f"[{decision_color}]{trade['decision']}[/{decision_color}]",
                f"{trade['price']:.4f}",
                f"{trade['quantity']:.4f}",
            )
    
    return Panel(Align.center(table), title="[bold white]Trade History[/bold white]", border_style="bright_green")


def get_latest_status_data():
    """Queries the DB and returns the data from the last StatusLog."""
    db = SessionLocal()
    try:
        latest_status = db.query(StatusLog).order_by(StatusLog.timestamp.desc()).first()
        if not latest_status:
            return None
        return {
            'timestamp': latest_status.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'strategy': latest_status.strategy,
            'signal': latest_status.signal,
            'close_price': latest_status.close_price,
            'rsi': latest_status.rsi,
            'balance_usdt': latest_status.balance_usdt,
        }
    finally:
        db.close()

def get_all_trades_data(limit: int = 10):
    """Queries the DB and returns the last 'limit' trades."""
    db = SessionLocal()
    try:
        trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(limit).all()
        return [
            {
                'id': trade.id,
                'timestamp': trade.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                'symbol': trade.symbol,
                'decision': trade.decision,
                'price': trade.price,
                'quantity': trade.quantity,
            }
            for trade in trades
        ]
    finally:
        db.close()

def update_monitor_display(layout: Layout):
    """Updates the monitor panels with the most recent data."""
    latest_status = get_latest_status_data()
    recent_trades = get_all_trades_data()

    layout["header"].update(Panel(
        f"[bold blue]Trading Bot Monitor[/bold blue] - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        border_style="blue",
        title_align="center",
        height=3
    ))
    layout["left_pane"].update(make_status_table(latest_status))
    layout["right_pane"].update(make_trades_table(recent_trades))

if __name__ == "__main__":
    app_layout = make_layout()    
    with Live(app_layout, screen=True, refresh_per_second=4, console=console) as live:
        try:
            while True:
                update_monitor_display(app_layout)
                time.sleep(1) # Update every 1 second
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Monitor stopped by user.[/bold yellow]")
        except Exception as e:
            console.print(f"\n[bold red]Critical error in monitor! {e}[/bold red]")
            sys.exit(1)
