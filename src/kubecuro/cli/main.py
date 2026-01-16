#!/usr/bin/env python3
"""
KUBECURO CLI - Side-by-Side UI (Phase 1.2)
------------------------------------------
Primary interface updated to support vertical split-screen comparisons
and high-fidelity comment-aware rendering.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Rich library components for high-fidelity terminal UI
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import (
    Progress, 
    SpinnerColumn, 
    TextColumn, 
    TimeElapsedColumn, 
    BarColumn, 
    TaskProgressColumn
)
from rich.syntax import Syntax

# Core Engine import
from kubecuro.core.engine import AuditEngineV3

# Global console for consistent styling across the application
console = Console()

class KubeCuroCLI:
    """
    CLI wrapper that translates user commands into Engine actions.
    Provides visual feedback, safety confirmations, and side-by-side diffs.
    """

    def __init__(self):
        """Initializes the CLI and sets up the argument parser."""
        self.parser = argparse.ArgumentParser(
            prog="kubecuro",
            description="KubeCuro - Kubernetes Logic Diagnostics & YAML Auto-Healer",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Learn more: https://github.com/fixmyk8s/kubecuro"
        )
        self._setup_args()

    def _get_catalog_path(self) -> str:
        """
        Retrieves the location of the K8s schema catalog dynamically.
        Uses relative pathing to ensure the tool is portable across environments.
        """
        # Start at the directory of the current script
        base_path = Path(__file__).resolve().parent
        
        # Check standard locations: same dir, parent (src), or root
        search_locations = [
            base_path / "catalog" / "k8s_v1_distilled.json",
            base_path.parent / "catalog" / "k8s_v1_distilled.json",
            base_path.parent.parent / "catalog" / "k8s_v1_distilled.json"
        ]

        for candidate in search_locations:
            if candidate.exists():
                return str(candidate)
        
        return ""

    def _setup_args(self):
        """Configures the command-line flags and subcommands."""
        self.parser.add_argument("-v", "--version", action="version", version="kubecuro v1.0.0")
        subparsers = self.parser.add_subparsers(dest="command", metavar="Command")

        # 'fix' subcommand - The active healing mode
        fix_parser = subparsers.add_parser("fix", help="❤️ Auto-heal YAML manifests")
        fix_parser.add_argument("path", help="Path to a YAML file or directory")
        fix_parser.add_argument("--dry-run", action="store_true", help="Preview results without writing")
        fix_parser.add_argument("--diff", action="store_true", help="Display vertical split comparison")
        fix_parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm single file")
        fix_parser.add_argument("--yes-all", action="store_true", help="Auto-confirm batch operations")
        fix_parser.add_argument("--force", action="store_true", help="Force write even partial heals")
        fix_parser.add_argument("--ext", default=".yaml", help="File extension filter (default: .yaml)")
        fix_parser.add_argument("--strict", action="store_true", help="Fail if unknown fields (typos) are found")

        # 'scan' subcommand - Read-only audit mode
        scan_parser = subparsers.add_parser("scan", help="🔍 Audit manifests for errors")
        scan_parser.add_argument("path", help="Path to scan")
        scan_parser.add_argument("--ext", default=".yaml", help="File extension filter")
        scan_parser.add_argument("--diff", action="store_true", help="Show suggested changes in preview")
        scan_parser.add_argument("--strict", action="store_true", help="Fail if unknown fields (typos) are found")

    def print_header(self, subtitle: str):
        """Renders the KubeCuro splash header with themed styling."""
        console.print(Panel.fit(
            "[bold cyan]KubeCuro v1.0.0[/bold cyan]\n"
            "══════════════════════════════════════════════════════════════════",
            title=f"[bold white]{subtitle}[/bold white]",
            border_style="cyan"
        ))

    def _show_side_by_side_diff(self, file_path: str, old_content: str, new_content: str):
        """
        Renders side-by-side comparison. Height is removed to allow natural 
        scrolling for large manifests.
        """
        old_syntax = Syntax(old_content.strip(), "yaml", theme="ansi_dark", line_numbers=True)
        new_syntax = Syntax(new_content.strip(), "yaml", theme="monokai", line_numbers=True)

        layout_table = Table.grid(expand=True, padding=1)
        layout_table.add_column(ratio=1) 
        layout_table.add_column(ratio=1) 

        layout_table.add_row(
            Panel(old_syntax, title=f"[bold red]ORIGINAL: {file_path}[/bold red]", border_style="red"),
            Panel(new_syntax, title=f"[bold green]HEALED: {file_path}[/bold green]", border_style="green")
        )
        console.print(layout_table)

    def _show_shield_logs(self, logs: List[str]):
        """Displays notifications from the Logic Shield policy engine."""
        for log in logs:
            console.print(f"🛡️  [bold cyan]SHIELD POLICY:[/bold cyan] [white]{log}[/white]")

    def _confirm_action(self, target_count: int, args: argparse.Namespace) -> bool:
        """Safety Gate logic: ensures the user wants to proceed with writes."""
        if args.dry_run:
            return True
        
        if target_count == 1:
            if args.yes or args.yes_all:
                return True
            choice = console.input("\n[bold yellow]Apply fix to this file? (y/N): [/bold yellow]").lower()
            return choice == 'y'
        
        if target_count > 1:
            if args.yes_all:
                return True
            
            console.print(Panel(
                f"[bold red]⚠️  CRITICAL: BATCH MODIFICATION DETECTED[/bold red]\n\n"
                f"Target Path: [white]{args.path}[/white]\n"
                f"File Count:  [bold cyan]{target_count} files[/bold cyan]\n",
                expand=False, border_style="red"
            ))

            prompt_text = f"[bold yellow]Type 'CONFIRM' to execute fixes: [/bold yellow]"
            user_input = console.input(prompt_text)
            return user_input == "CONFIRM"
        
        return False

    def _run_engine(self, args: argparse.Namespace, is_fix_mode: bool):
        """Main processing loop orchestration."""
        input_path = Path(args.path).resolve()
        if not input_path.exists():
            console.print(f"[bold red]Error:[/bold red] Path '{args.path}' not found.")
            return

        workspace = input_path if input_path.is_dir() else input_path.parent
        catalog_path = self._get_catalog_path()
        if not catalog_path:
            console.print("[bold red]CRITICAL ERROR:[/bold red] Schema catalog is missing.")
            sys.exit(1)

        engine = AuditEngineV3(str(workspace), catalog_path)
        
        # Determine targets (single file vs recursive directory)
        if input_path.is_file():
            target_files = [input_path]
        else:
            target_files = sorted([
                f for f in input_path.rglob(f"*{args.ext}") 
                if f.is_file() and not f.is_symlink()
            ])

        if not target_files:
            console.print(f"\n[bold yellow]⚠️  No valid YAML files found.[/bold yellow]")
            return

        # Confirm before starting if we are in fix mode
        if is_fix_mode and not self._confirm_action(len(target_files), args):
            console.print("[bold red]Operation cancelled by user.[/bold red]")
            return

        reports = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            
            task_id = progress.add_task("Processing manifests...", total=len(target_files))
            
            for file_path in target_files:
                try:
                    rel_path = str(file_path.relative_to(workspace))
                    old_content = file_path.read_text(encoding='utf-8-sig')

                    # Core execution
                    report = engine.audit_and_heal_file(
                        rel_path,
                        dry_run=args.dry_run or not is_fix_mode,
                        force_write=getattr(args, 'force', False),
                        strict=args.strict
                    )
                    reports.append(report)

                    # Toggle diff UI if requested
                    if args.diff and report.get('healed_content'):
                        progress.stop()
                        console.print(f"\n[bold cyan]Analysis for: {rel_path}[/bold cyan]")
                        
                        if report.get("logic_logs"):
                            self._show_shield_logs(report["logic_logs"])
                            
                        self._show_side_by_side_diff(rel_path, old_content, report['healed_content'])
                        console.print("─" * console.width)
                        progress.start()

                except Exception as e:
                    reports.append({
                        "file_path": file_path.name, "status": "ENGINE_ERROR", 
                        "error": str(e), "success": False, "kind": "Unknown"
                    })

                progress.update(task_id, advance=1, description=f"Checked: {file_path.name}")

        self._render_final_report(reports, engine)

    def _render_final_report(self, reports: List[Dict], engine: Any):
        """Constructs the final summary table and metrics panel for the user."""
        table = Table(title="KubeCuro Execution Report", show_lines=True, header_style="bold magenta")
        table.add_column("File Path", style="cyan")
        table.add_column("Kind", style="white")
        table.add_column("Status", style="bold")
        table.add_column("Result", justify="center")

        for r in reports:
            if r.get('status') == "ENGINE_ERROR":
                console.print(f"[bold red]Error in {r['file_path']}:[/bold red] {r.get('error')}")
            
            success = r.get('success', False)
            partial = r.get('partial_heal', False)
            status_color = "green" if success else "yellow" if partial else "red"
            result_icon = "✅" if success else "⚠️" if partial else "❌"
            
            table.add_row(
                str(r.get('file_path')), str(r.get('kind', 'Unknown')),
                f"[{status_color}]{r.get('status', 'FAILED')}[/{status_color}]",
                result_icon
            )

        console.print(table)
        summary = engine.generate_summary(reports)
        console.print(Panel(
            f"[bold white]Summary Report[/bold white]\n"
            f"════════════════════════════════════════\n"
            f"Total Files:     {summary['total_files']}\n"
            f"Success:        [green]{summary['successful']}[/green]\n"
            f"System Errors:  [red]{summary['system_errors']}[/red]\n"
            f"Backups Created: {summary['backups_created']}",
            border_style="dim"
        ))

    def run(self):
        """Primary routing entry point."""
        if len(sys.argv) == 1:
            self.print_header("K8s Diagnostics & Healer")
            self.parser.print_help()
            sys.exit(0)

        args = self.parser.parse_args()
        if args.command == "scan":
            self.print_header("Logic Audit Scan")
            self._run_engine(args, is_fix_mode=False)
        elif args.command == "fix":
            self.print_header("YAML Auto-Heal Engine")
            self._run_engine(args, is_fix_mode=True)
        else:
            self.parser.print_help()

def main():
    """Application entry point with interrupt handling."""
    print("🚀 KubeCuro v0.1.0 starting...")
    try:
        KubeCuroCLI().run()
    except KeyboardInterrupt:
        console.print("\n[bold red]Terminated by user.[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
