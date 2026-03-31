"""Welcome banner for IO CLI.

Custom branding and welcome message for Gotenks fusion.
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


def get_welcome_banner() -> str:
    """Get the IO welcome banner ASCII art."""
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ██╗ ██████╗     ████████╗██╗  ██╗███████╗    ███████╗██╗   ██╗███████╗███████╗██╗ ██████╗ ███╗   ██╗
║   ██║██╔═══██╗    ╚══██╔══╝██║  ██║██╔════╝    ██╔════╝██║   ██║██╔════╝██╔════╝██║██╔═══██╗████╗  ██║
║   ██║██║   ██║       ██║   ███████║█████╗      █████╗  ██║   ██║█████╗  █████╗  ██║██║   ██║██╔██╗ ██║
║   ██║██║   ██║       ██║   ██╔══██║██╔══╝      ██╔══╝  ╚██╗ ██╔╝██╔══╝  ██╔══╝  ██║██║   ██║██║╚██╗██║
║   ██║╚██████╔╝       ██║   ██║  ██║███████╗    ██║      ╚████╔╝ ███████╗██║     ██║╚██████╔╝██║ ╚████║
║   ╚═╝ ╚═════╝        ╚═╝   ╚═╝  ╚═╝╚══════╝    ╚═╝       ╚═══╝  ╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
║                                                                  ║
║                    Gotenks Fusion v0.2.0 🌀                       ║
║                                                                  ║
║         Combining the best of pi-mono, Hermes, and Gauss         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """
    return banner


def print_welcome(console: Console = None) -> None:
    """Print the welcome banner with styling."""
    if console is None:
        console = Console()

    # Create styled text
    text = Text()
    text.append("IO", style="bold cyan")
    text.append(" - ", style="dim")
    text.append("Gotenks Fusion", style="bold yellow")
    text.append(" v0.2.0", style="dim")
    text.append(" 🌀\n", style="")
    text.append("The fusion of pi-mono, Hermes, and Gauss\n", style="dim")
    text.append("8 packages, 100% Gauss parity, RL-ready\n", style="dim green")

    panel = Panel(
        text,
        title="[bold blue]Welcome to IO[/bold blue]",
        subtitle="[dim]Type /help for available commands[/dim]",
        border_style="blue",
    )

    console.print(panel)

    # Print quick tips
    console.print("\n[dim]Quick start:[/dim]")
    console.print("  [cyan]io chat[/cyan]              Start interactive chat")
    console.print("  [cyan]io swarm list[/cyan]        View running agents")
    console.print('  [cyan]io prove "theorem"[/cyan]   Spawn proof agent')
    console.print("  [cyan]io mini-swe run[/cyan]      Run SWE benchmark")
    console.print()


def get_compact_banner() -> str:
    """Get compact one-line banner for status bar."""
    return "[bold cyan]IO[/bold cyan] [dim]v0.2.0[/dim] [yellow]🌀[/yellow]"
