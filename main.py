#!/usr/bin/env python3
"""
LinkedIn Outreach Automator for Storylane Customer Influencer Program.

Usage:
    python main.py                     # Run full pipeline (resolve -> enrich -> connect -> message)
    python main.py resolve             # Only resolve post URLs to profiles
    python main.py enrich              # Only enrich profiles and score candidates
    python main.py connect             # Only send connection requests
    python main.py message             # Only message connected contacts
    python main.py follow-up           # Send follow-up messages
    python main.py summary             # Print summary of current state
    python main.py export              # Export results to CSV
    python main.py check-connections   # Re-check connection statuses and message new acceptances
    python main.py find-users          # Search LinkedIn for potential Storylane users
    python main.py dry-run             # Run enrichment + scoring without sending any messages
"""

import sys
import logging

from rich.console import Console
from rich.logging import RichHandler

from linkedin_client import LinkedInClient
from outreach_manager import OutreachManager

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)
console = Console()


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "full"

    client = LinkedInClient()

    if command == "summary":
        manager = OutreachManager(client)
        manager.load_contacts()
        manager.print_summary()
        return

    if command == "export":
        manager = OutreachManager(client)
        manager.load_contacts()
        manager.export_results()
        return

    console.print("[bold]Authenticating with LinkedIn...[/bold]")
    if not client.authenticate():
        console.print("[red]Authentication failed. Check your .env credentials.[/red]")
        sys.exit(1)
    console.print("[green]Authenticated successfully![/green]\n")

    manager = OutreachManager(client)
    manager.load_contacts()

    if command == "full":
        console.print("[bold cyan]Running full outreach pipeline...[/bold cyan]\n")
        manager.resolve_profiles()
        manager.enrich_profiles()
        manager.send_connection_requests()
        manager.message_connected_contacts()
        manager.print_summary()
        manager.export_results()

    elif command == "resolve":
        manager.resolve_profiles()

    elif command == "enrich":
        manager.enrich_profiles()
        manager.print_summary()

    elif command == "connect":
        manager.send_connection_requests()

    elif command == "message":
        manager.message_connected_contacts()

    elif command == "follow-up":
        manager.send_follow_ups()

    elif command == "check-connections":
        manager.message_connected_contacts()

    elif command == "find-users":
        console.print("[bold cyan]Searching for potential Storylane users...[/bold cyan]")
        searches = [
            "product marketing manager interactive demo",
            "presales solutions engineer demo",
            "demand generation SaaS product-led growth",
            "sales enablement B2B SaaS",
        ]
        all_results = []
        for query in searches:
            console.print(f"Searching: {query}")
            results = client.search_people(keywords=query, limit=10)
            all_results.extend(results)
            console.print(f"  Found {len(results)} results")

        seen = set()
        unique = []
        for r in all_results:
            pid = r.get("public_id", "")
            if pid and pid not in seen:
                seen.add(pid)
                unique.append(r)

        console.print(f"\n[bold]Found {len(unique)} unique potential users:[/bold]")
        for r in unique:
            name = f"{r.get('name', '?')}"
            headline = r.get("jobtitle", "") or r.get("headline", "")
            console.print(f"  - {name} | {headline} | linkedin.com/in/{r.get('public_id', '')}")

    elif command == "dry-run":
        console.print("[bold yellow]DRY RUN — enriching and scoring only, no messages will be sent[/bold yellow]\n")
        manager.resolve_profiles()
        manager.enrich_profiles()
        manager.print_summary()
        manager.export_results("dry_run_results.csv")

    else:
        console.print(f"[red]Unknown command: {command}[/red]")
        console.print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
