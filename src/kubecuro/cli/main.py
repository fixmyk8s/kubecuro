#!/usr/bin/env python3
"""
KUBECURO CLI - The Primary Interface
------------------------------------
Orchestrates healing and scanning operations for Kubernetes manifests. 
Includes multi-path catalog discovery, symlink protection, and 
manifest-specific safety gates.

Author: Nishar A Sunkesala / KubeCuro Team
Date: 2026-01-16
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any

import click
import rich_click as rich_click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.syntax import Syntax
from rich import box

# Core Engine Import
from kubecuro.core.engine import AuditEngineV3

# --- UI & GLOBAL CONFIGURATION ---
console = Console()

# Unicode constants for fixed-width alignment in help menus
# En Quad (U+2000) provides a stable gap after emojis
GAP = "\u2000" 

rich_click.USE_RICH_MARKUP = True
rich_click.STYLE_HELPTEXT = "italic dim"
rich_click.MAX_WIDTH = 100 
rich_click.SHOW_ARGUMENTS = True
rich_click.GROUP_ARGUMENTS_OPTIONS = True

def print_header():
    """
    Displays the application banner only on an empty CLI call.
    """
    if len(sys.argv) == 1:
        console.print("🚀 KubeCuro v1.0.0 starting...", style="bold yellow")
        banner_content = (
            "[bold cyan]Kubernetes Logic Diagnostics & YAML Auto-Healer[/bold cyan]\n"
            "[italic white]Heal your K8s manifests with logic-aware diagnostics.[/italic white]"
        )
        console.print(Panel(banner_content, border_style="blue", expand=False))

def show_shield_logs(logs: List[str]):
    """
    Renders Logic Shield policy engine logs with distinct iconography.
    """
    for log in logs:
        console.print(f"🛡️  [bold cyan]SHIELD POLICY:[/bold cyan] [white]{log}[/white]")

def show_git_warnings(warnings: List[str]):
    """
    Renders Git configuration warnings if KubeCuro artifacts are not ignored.
    """
    if not warnings:
        return
    
    unique_warnings = sorted(list(set(warnings)))
    warning_content = "\n".join([f"• [bold yellow]{w}[/bold yellow]" for w in unique_warnings])
    
    console.print(Panel(
        f"[bold red]⚠️  VCS SAFETY WARNING[/bold red]\n\n"
        f"KubeCuro detected that temporary artifacts are not ignored in your .gitignore:\n{warning_content}",
        border_style="red",
        title="[white]Git Configuration[/white]",
        expand=False
    ))

def show_side_by_side_diff(file_path: str, old_content: str, new_content: str):
    """
    Renders a side-by-side YAML comparison using a layout grid for responsiveness.
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
    console.print("─" * console.width)

# --- CLI DEFINITION ---

@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]} 
)
@click.version_option(
    "1.0.0", "-v", "--version", 
    prog_name="kubecuro",        
    message="🚀 KubeCuro v%(version)s"
)
@click.pass_context
def cli(ctx):
    """KubeCuro: Heal your K8s manifests with logic-aware diagnostics."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--diff", is_flag=True, help="Show suggested changes in preview.")
@click.option("--max-depth", default=10, type=int, help="Max recursion depth.")
@click.option("--ext", default=".yaml", help="File extension.")
@click.option("--strict", is_flag=True, help="Fail on unknown fields.")
def scan(path, diff, max_depth, ext, strict):
    f"""\U0001f50d{GAP}Audit K8s manifests for errors without making changes."""
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
    f"""\u2764\ufe0f{GAP}Auto-heal K8s manifests and fix logical errors."""
    run_processing_loop(path, dry_run, diff, max_depth, ext, strict, force, yes, yes_all)

# --- CORE LOGIC ORCHESTRATOR ---

def run_processing_loop(path, dry_run, diff, max_depth, ext, strict, force=False, yes=False, yes_all=False):
    """
    Core loop for manifest processing. Handles discovery and batch safety confirmations.
    """
    input_path = Path(path).resolve()
    workspace = input_path if input_path.is_dir() else input_path.parent
    
    # Catalog Discovery Logic
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
    
    # Discovery with Symlink Protection
    if input_path.is_file():
        target_files = [input_path]
    else:
        target_files = sorted([f for f in input_path.rglob(f"*{ext}") if f.is_file() and not f.is_symlink()])

    if not target_files:
        console.print(f"\n[bold yellow]⚠️  No valid {ext} manifests found.[/bold yellow]")
        return

    # Safety Gate: Bulk confirmation
    if not dry_run:
        if len(target_files) > 1 and not yes_all:
            console.print(Panel(
                f"[bold red]⚠️  SAFETY GATE: BULK MANIFEST MODIFICATION[/bold red]\n\n"
                f"Preparing to auto-heal [bold cyan]{len(target_files)}[/bold cyan] Kubernetes manifests.\n"
                f"Target Path: [white]{path}[/white]\n",
                expand=False, border_style="red"
            ))
            if click.prompt("[bold yellow]Type 'CONFIRM' to apply logical fixes[/bold yellow]", default="") != "CONFIRM":
                console.print("[bold red]Action aborted by user. No files modified.[/bold red]")
                return
        elif len(target_files) == 1 and not (yes or yes_all):
            if not click.confirm(f"[bold yellow]Apply healing to manifest: {target_files[0].name}?[/bold yellow]"):
                return

    reports = []

    # Manifest Processing Progress Bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Processing:[/bold blue] [progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False 
    ) as progress:
        task = progress.add_task("Analyzing manifests...", total=len(target_files))
        
        for file_path in target_files:
            try:
                rel_parts = file_path.relative_to(workspace).parts
                if len(rel_parts) > max_depth:
                    progress.advance(task)
                    continue

                rel_path = str(file_path.relative_to(workspace))
                progress.update(task, description=f"[cyan]{rel_path}[/cyan]")
                
                old_content = file_path.read_text(encoding='utf-8-sig')
                report = engine.audit_and_heal_file(rel_path, dry_run=dry_run, force_write=force, strict=strict)
                reports.append(report)

                if diff and report.get('healed_content'):
                    progress.stop()
                    console.print(f"\n[bold cyan]Diagnostic Analysis for: {rel_path}[/bold cyan]")
                    if report.get("logic_logs"):
                        show_shield_logs(report["logic_logs"])
                    show_side_by_side_diff(rel_path, old_content, report['healed_content'])
                    progress.start()
                
                progress.advance(task)

            except Exception as e:
                reports.append({
                    "file_path": file_path.name, "status": "ENGINE_ERROR", 
                    "error": str(e), "success": False, "kind": "Unknown", "git_warnings": []
                })
                progress.advance(task)

        progress.update(task, description="[bold green]Manifest logical integrity restored successfully[/bold green]")

    render_summary(reports, engine)

def render_summary(reports: List[Dict], engine: Any):
    """
    Constructs final execution tables, git safety warnings, and summary panels.
    """
    table = Table(
        title="\n[bold magenta]KubeCuro Scan Execution Report[/bold magenta]", 
        show_lines=True, 
        header_style="bold",
        box=box.MINIMAL_HEAVY,
        expand=True
    )
    table.add_column("Manifest Path", style="cyan", no_wrap=False)
    table.add_column("Kind", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Result", justify="center")
    
    all_git_warnings = []

    for r in reports:
        if r.get('status') == "ENGINE_ERROR":
            console.print(f"[bold red]Error in manifest {r['file_path']}:[/bold red] {r.get('error')}")

        success = r.get('success', False)
        partial = r.get('partial_heal', False)
        color = "green" if success else "yellow" if partial else "red"
        icon = "✅" if success else "⚠️" if partial else "❌"
        
        # Aggregate git warnings for final display
        if r.get("git_warnings"):
            all_git_warnings.extend(r["git_warnings"])

        table.add_row(
            str(r.get('file_path')), 
            str(r.get('kind', 'Unknown')), 
            f"[{color}]{r.get('status', 'FAILED')}[/{color}]", 
            icon
        )
    
    console.print(table)

    # Show consolidated Git Warnings if they exist
    show_git_warnings(all_git_warnings)

    summary = engine.generate_summary(reports)
    
    summary_text = (
        f"[bold white]Manifest Scan Summary Report[/bold white]\n"
        f"════════════════════════════════════════\n"
        f"Total Manifests: {summary['total_files']}\n"
        f"Healed/Valid:    [green]{summary['successful']}[/green]\n"
        f"System Errors:   [red]{summary.get('system_errors', 0)}[/red]\n"
        f"Backups Created: {summary.get('backups_created', 0)}"
    )
    console.print(Panel(summary_text, border_style="dim", expand=False))

if __name__ == "__main__":
    print_header()
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[bold red]Operation terminated by user.[/bold red]")
        sys.exit(1)
