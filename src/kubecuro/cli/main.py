#!/usr/bin/env python3
"""
KUBECURO CLI - Side-by-Side UI (Phase 1.2)
------------------------------------------
Finalized Click-based interface. 100% logic parity with Argparse version,
including multi-path catalog discovery and robust batch exception handling.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

import click
import rich_click as click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.syntax import Syntax

from kubecuro.core.engine import AuditEngineV3

# --- UI Configuration ---
console = Console()
click.rich_click.USE_RICH_MARKUP = True
click.rich_click.HEADER_TEXT = "[bold cyan]KubeCuro - Kubernetes Logic Diagnostics & YAML Auto-Healer[/bold cyan]"

def show_shield_logs(logs: List[str]):
    """Explicitly displays notifications from the Logic Shield policy engine."""
    for log in logs:
        console.print(f"🛡️  [bold cyan]SHIELD POLICY:[/bold cyan] [white]{log}[/white]")

def show_side_by_side_diff(file_path: str, old_content: str, new_content: str):
    """Renders a vertical side-by-side comparison of YAML content."""
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
    console.print("─" * console.width)

# --- CLI Core ---

@click.group(invoke_without_command=True)
@click.version_option("1.0.0", prog_name="kubecuro")
@click.pass_context
def cli(ctx):
    """KubeCuro: Heal your K8s manifests with logic-aware diagnostics."""
    if ctx.invoked_subcommand is None:
        console.print(Panel.fit("[bold cyan]KubeCuro v1.0.0[/bold cyan]", border_style="cyan"))
        click.echo(ctx.get_help())

@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--diff", is_flag=True, help="Show suggested changes in preview.")
@click.option("--max-depth", default=10, type=int, help="Max recursion depth.")
@click.option("--ext", default=".yaml", help="File extension.")
@click.option("--strict", is_flag=True, help="Fail on unknown fields.")
def scan(path, diff, max_depth, ext, strict):
    """🔍 Audit manifests for errors without making changes."""
    run_processing_loop(path, dry_run=True, diff=diff, max_depth=max_depth, ext=ext, strict=strict)

@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview results without writing.")
@click.option("--diff", is_flag=True, help="Display vertical split comparison.")
@click.option("--yes", "-y", is_flag=True, help="Auto-confirm single file.")
@click.option("--yes-all", is_flag=True, help="Auto-confirm batch operations.")
@click.option("--force", is_flag=True, help="Force write even partial heals.")
@click.option("--max-depth", default=10, type=int, help="Max recursion depth.")
@click.option("--ext", default=".yaml", help="File extension.")
@click.option("--strict", is_flag=True, help="Fail on unknown fields.")
def fix(path, dry_run, diff, yes, yes_all, force, max_depth, ext, strict):
    """❤️  Auto-heal YAML manifests and fix logical errors."""
    run_processing_loop(path, dry_run, diff, max_depth, ext, strict, force, yes, yes_all)

# --- The Logic Orchestrator ---

def run_processing_loop(path, dry_run, diff, max_depth, ext, strict, force=False, yes=False, yes_all=False):
    input_path = Path(path).resolve()
    workspace = input_path if input_path.is_dir() else input_path.parent
    
    # 1. RESTORED: Robust Multi-path catalog discovery logic
    base_path = Path(__file__).resolve().parent
    search_locations = [
        base_path / "catalog" / "k8s_v1_distilled.json",
        base_path.parent / "catalog" / "k8s_v1_distilled.json",
        Path("catalog/k8s_v1_distilled.json")
    ]
    
    catalog = ""
    for loc in search_locations:
        if loc.exists():
            catalog = str(loc)
            break
            
    if not catalog:
        console.print("[bold red]CRITICAL ERROR:[/bold red] Schema catalog is missing.")
        sys.exit(1)

    engine = AuditEngineV3(str(workspace), catalog)
    
    # 2. Discovery with Symlink Protection
    if input_path.is_file():
        target_files = [input_path]
    else:
        target_files = sorted([f for f in input_path.rglob(f"*{ext}") if f.is_file() and not f.is_symlink()])

    if not target_files:
        console.print(f"\n[bold yellow]⚠️  No valid {ext} files found.[/bold yellow]")
        return

    # 3. RESTORED: CRITICAL BATCH SAFETY GATE
    if not dry_run:
        if len(target_files) > 1 and not yes_all:
            console.print(Panel(
                f"[bold red]⚠️  CRITICAL: BATCH MODIFICATION DETECTED[/bold red]\n\n"
                f"Target Path: [white]{path}[/white]\n"
                f"File Count:  [bold cyan]{len(target_files)} files[/bold cyan]\n",
                expand=False, border_style="red"
            ))
            if click.prompt("[bold yellow]Type 'CONFIRM' to execute fixes[/bold yellow]", default="") != "CONFIRM":
                console.print("[bold red]Operation cancelled by user.[/bold red]")
                return
        elif len(target_files) == 1 and not (yes or yes_all):
            if not click.confirm(f"[bold yellow]Apply fix to {target_files[0].name}?[/bold yellow]"):
                return

    reports = []
    # Using the enhanced Progress bar with TimeElapsed (Restored from old version)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Processing manifests...", total=len(target_files))
        
        for file_path in target_files:
            try:
                # Restored: Explicit Depth Check logic
                rel_parts = file_path.relative_to(workspace).parts
                if len(rel_parts) > max_depth:
                    progress.advance(task)
                    continue

                rel_path = str(file_path.relative_to(workspace))
                old_content = file_path.read_text(encoding='utf-8-sig')
                
                report = engine.audit_and_heal_file(rel_path, dry_run=dry_run, force_write=force, strict=strict)
                reports.append(report)

                # 4. RESTORED: Side-by-Side Diff Triggering
                if diff and report.get('healed_content'):
                    progress.stop()
                    console.print(f"\n[bold cyan]Analysis for: {rel_path}[/bold cyan]")
                    if report.get("logic_logs"):
                        show_shield_logs(report["logic_logs"])
                    show_side_by_side_diff(rel_path, old_content, report['healed_content'])
                    progress.start()
                
                progress.update(task, advance=1, description=f"Checked: {file_path.name}")

            except Exception as e:
                # 5. RESTORED: Loop-safety exception handling
                reports.append({
                    "file_path": file_path.name, "status": "ENGINE_ERROR", 
                    "error": str(e), "success": False, "kind": "Unknown"
                })
                progress.advance(task)

    render_summary(reports, engine)

def render_summary(reports, engine):
    """Constructs the final summary table and metrics panel."""
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
        color = "green" if success else "yellow" if partial else "red"
        icon = "✅" if success else "⚠️" if partial else "❌"
        
        table.add_row(
            str(r.get('file_path')), 
            str(r.get('kind', 'Unknown')), 
            f"[{color}]{r.get('status', 'FAILED')}[/{color}]", 
            icon
        )
    
    console.print(table)
    summary = engine.generate_summary(reports)
    
    # Restored: Detailed Summary Panel
    console.print(Panel(
        f"[bold white]Summary Report[/bold white]\n"
        f"════════════════════════════════════════\n"
        f"Total Files:     {summary['total_files']}\n"
        f"Success:         [green]{summary['successful']}[/green]\n"
        f"System Errors:   [red]{summary.get('system_errors', 0)}[/red]\n"
        f"Backups Created: {summary.get('backups_created', 0)}",
        border_style="dim"
    ))

if __name__ == "__main__":
    # RESTORED: The startup greeting
    print("\033[1;33m🚀  KubeCuro v1.0.0 starting...\033[0m")
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[bold red]Terminated by user.[/bold red]")
        sys.exit(1)
