#!/usr/bin/env python3
"""
KUBECURO CLI - Production Hardened
----------------------------------
Orchestrates: 
1. Subcommand Routing (scan/fix)
2. Safety Gates (Confirmation & Batch Protection)
3. Visual Diffing (--diff)
4. Progress Tracking & SRE Summary
"""

import sys
import time
import argparse
import difflib
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, BarColumn, TaskProgressColumn
from rich.syntax import Syntax

# Internal Package Imports
from kubecuro.core.engine import AuditEngineV2

console = Console()

class KubeCuroCLI:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            prog="kubecuro",
            description="KubeCuro - Kubernetes Logic Diagnostics & YAML Auto-Healer",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Learn more: https://github.com/nisharas/kubecuro"
        )
        self._setup_args()

    def _setup_args(self):
        # Global Utility Flags
        self.parser.add_argument("-v", "--version", action="version", version="kubecuro v1.0.0")
        self.parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to disk")
        self.parser.add_argument("--diff", action="store_true", help="Show line-by-line diff of proposed changes")

        subparsers = self.parser.add_subparsers(dest="command", metavar="Command")

        # ❤️ Fix Command
        fix_parser = subparsers.add_parser("fix", help="❤️  Auto-heal YAML files (Characters & Structure)")
        fix_parser.add_argument("path", help="Path to file or directory")
        fix_parser.add_argument("-y", "--yes", action="store_true", help="Confirm fix for a single file")
        fix_parser.add_argument("--yes-all", action="store_true", help="Bypass manual confirmation for batch fixes (requires 'CONFIRM' prompt)")
        fix_parser.add_argument("--force", action="store_true", help="Force write even on partial structural heals")
        fix_parser.add_argument("--ext", default=".yaml", help="File extension to target (default: .yaml)")

        # 🔍 Scan Command
        scan_parser = subparsers.add_parser("scan", help="🔍 Scan for logic errors (Read-Only)")
        scan_parser.add_argument("path", help="Path to scan")
        scan_parser.add_argument("--ext", default=".yaml", help="File extension to target")

    def print_header(self, subtitle: str):
        """Standardized Tool Header."""
        console.print(Panel.fit(
            "[bold cyan]KubeCuro v1.0.0[/bold cyan]\n"
            "══════════════════════════════════════════════════════════════════",
            title=f"[bold white]{subtitle}[/bold white]",
            border_style="cyan"
        ))

    def _show_diff(self, file_path: str, old_content: str, new_content: str):
        """Generates a colorized unified diff between original and healed content."""
        diff = difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"original/{file_path}",
            tofile=f"healed/{file_path}",
            lineterm=""
        )
        diff_text = "\n".join(list(diff))
        if diff_text:
            console.print(Syntax(diff_text, "diff", theme="monokai", background_color="default"))
        else:
            console.print(f"[dim]No changes detected for {file_path}[/dim]")

    def _confirm_action(self, target_count: int, args: argparse.Namespace) -> bool:
        """The Safety Gate: Protects against batch accidents and 'fat-fingering'."""
        if args.dry_run:
            return True
        
        if target_count == 1:
            if args.yes or args.yes_all:
                return True
            choice = console.input("\n[bold yellow]Apply fix to this file? (y/N): [/bold yellow]").lower()
            return choice == 'y'
        
        if target_count > 1:
            console.print(Panel(
                f"[bold red]⚠️  CRITICAL: BATCH MODIFICATION DETECTED[/bold red]\n\n"
                f"Target Path: [white]{args.path}[/white]\n"
                f"File Count:  [bold cyan]{target_count} files[/bold cyan]\n\n"
                f"This action will modify multiple files on disk. Backups will be created.",
                expand=False, border_style="red"
            ))

            prompt_text = f"[bold yellow]Type 'CONFIRM' to execute fixes on {target_count} files: [/bold yellow]"
            user_input = console.input(prompt_text)

            if user_input == "CONFIRM":
                if args.yes_all:
                    console.print("[dim]Batch flag detected. Starting in 1 second...[/dim]")
                    time.sleep(1)
                return True
            else:
                console.print("[bold red]Confirmation failed. Operation aborted.[/bold red]")
                return False
        
        return False

    def _run_engine(self, args: argparse.Namespace, is_fix_mode: bool):
        """Main execution engine for both scan and fix commands."""
        workspace = Path(args.path).resolve()
        
        if workspace in [Path("/"), Path.home()]:
            console.print("[bold red]SAFETY ERROR:[/bold red] Running KubeCuro on Root or Home directory is prohibited.")
            sys.exit(1)

        if not workspace.exists():
            console.print(f"[bold red]Error:[/bold red] Path [white]'{workspace}'[/white] not found.")
            return

        engine = AuditEngineV2(str(workspace))
        
        # --- FIXED TARGET LIST LOGIC ---
        target_files = []
        all_matches_count = 0
        
        if workspace.is_file():
            target_files = [workspace]
        else:
            # 1. Collect all potential matches first
            all_matches = [f for f in workspace.rglob(f"*{args.ext}")]
            all_matches_count = len(all_matches)
            
            # 2. Filter for Symlinks and valid suffixes
            target_files = [
                f for f in all_matches 
                if f.is_file() and not f.is_symlink() and f.suffix.lower() in ['.yaml', '.yml']
            ]

        if not target_files:
            console.print(f"\n[bold yellow]⚠️  No valid YAML files found.[/bold yellow]")
            if all_matches_count > 0:
                console.print(f"[dim]Found {all_matches_count} files matching extension, but they were symlinks or invalid YAML suffixes.[/dim]")
            return

        if is_fix_mode and not self._confirm_action(len(target_files), args):
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
                rel_path = str(file_path.relative_to(workspace)) if workspace.is_dir() else file_path.name
                old_content = file_path.read_text(encoding='utf-8-sig') if file_path.exists() else ""

                report = engine.audit_and_heal_file(
                    rel_path,
                    dry_run=args.dry_run or not is_fix_mode,
                    force_write=getattr(args, 'force', False)
                )
                reports.append(report)

                if args.diff and report.get('content') != old_content:
                    progress.stop()
                    console.print(f"\n[bold cyan]Diff for {rel_path}:[/bold cyan]")
                    self._show_diff(rel_path, old_content, report.get('content', ''))
                    console.print("-" * 40)
                    progress.start()

                progress.update(task_id, advance=1, description=f"Analyzed: {file_path.name}")

        self._render_final_report(reports, engine, workspace, is_fix_mode, args)

    def _render_final_report(self, reports: List[Dict], engine: Any, path: Path, was_fix: bool, args: argparse.Namespace):
        table = Table(title="Audit & Heal Execution Report", show_lines=True, header_style="bold magenta")
        table.add_column("File Path", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Result", justify="center")
        table.add_column("Changes", justify="right")

        for r in (reports or []):
            success = r.get('success', False)
            partial = r.get('partial_heal', False)
            status_color = "green" if success else "yellow" if partial else "red"
            result_icon = "✅" if success else "⚠️" if partial else "❌"
            inner_report = r.get('report') or {}
            lines_changed = inner_report.get('lines_changed', 0) or 0
            
            table.add_row(
                str(r.get('file_path')),
                f"[{status_color}]{r.get('status')}[/{status_color}]",
                result_icon,
                str(lines_changed)
            )

        console.print(table)
        summary = engine.generate_summary(reports)
        console.print(f"\n[bold white]Final Summary:[/bold white]")
        console.print(f" • Files Scanned: {summary['total_files']}")
        console.print(f" • Success Rate: [bold green]{summary['success_rate']:.1%}[/bold green]")
        console.print(f" • Backups Created: {summary['backups_created']}")

        if args.dry_run:
            console.print(f"\n[bold cyan]Dry Run Mode:[/bold cyan] No files were modified. To apply, run:")
            console.print(f"[bold white]kubecuro fix {args.path}[/bold white]")
        elif not was_fix:
            console.print(f"\n[bold cyan]Scan Mode:[/bold cyan] Issues found. To repair, run:")
            console.print(f"[bold white]kubecuro fix {args.path}[/bold white]")
        elif summary.get('recommend_force_write'):
            console.print(f"\n[bold yellow]Partial Heals:[/bold yellow] Some files need structural force. Run:")
            console.print(f"[bold white]kubecuro fix {args.path} --force --yes-all[/bold white]")

    def run(self):
        if len(sys.argv) == 1:
            self.print_header("Kubernetes Logic Diagnostics & Healer")
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
            console.print("[yellow]Command not yet implemented.[/yellow]")

def main():
    try:
        KubeCuroCLI().run()
    except KeyboardInterrupt:
        console.print("\n[bold red]Terminated by user.[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
