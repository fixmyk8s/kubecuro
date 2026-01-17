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

rich_click.USE_RICH_MARKUP = True
rich_click.STYLE_HELPTEXT = "italic dim"
rich_click.MAX_WIDTH = 100 
rich_click.SHOW_ARGUMENTS = True
rich_click.GROUP_ARGUMENTS_OPTIONS = True

def print_header():
    """
    Displays the application banner only on an empty CLI call.
    """
    console.print("")
    console.print("🚀 KubeCuro v1.0.0 starting...", style="bold yellow")
    banner_content = (
        "[bold cyan]Kubernetes Logic Diagnostics & YAML Auto-Healer[/bold cyan]\n"
        "[dim italic]Fix broken K8s manifests instantly[/dim italic]"
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
@click.help_option("-h", "--help", help="Display help menu and available commands")
@click.version_option(
    "1.0.0", "-v", "--version", 
    prog_name="kubecuro",        
    message="KubeCuro Version: v%(version)s",
    help="Print version information"
    )

@click.option("--quiet", "-q", is_flag=True, help="Hide banner for scripts/automation")
@click.pass_context
def cli(ctx, quiet):
    ctx.info_name = "kubecuro"
    if not quiet and ctx.invoked_subcommand is None:
        print_header()
    
    if ctx.invoked_subcommand is None:
        console.print("\n[bold cyan]COMMANDS:[/bold cyan]")  # Custom header
        console.print("  scan    Audit manifests for issues")
        console.print("  fix     Apply logical healing and fix manifest errors")
        console.print("\n[bold cyan]GLOBAL OPTIONS:[/bold cyan]")
        console.print("  -q, --quiet     Hide banner for scripts/automation")
        console.print("  -v, --version   Print version information")
        console.print("  -h, --help      Show this help")
        console.print("\n[bold magenta]💡 TIP:[/bold magenta] Run [cyan]kubecuro scan/fix --help[/cyan] for options")

@cli.command(help="Audit manifests for issues")
@click.help_option("-h", "--help", help="Show detailed command help")
@click.argument("path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Choice(['table', 'json']), default='table', 
              help="Output format")
@click.option("--diff", is_flag=True, help="Show before/after previews")
@click.option("--strict", is_flag=True, help="Fail on unknown fields")
@click.option("--max-depth", type=int, default=10, 
              help="Max folder recursion depth (default: 10)")
@click.option("--ext", default=".yaml,.yml", 
              help="File extensions (default: .yaml,.yml)")
def scan(path, diff, max_depth, ext, strict, output):
    """Audit K8s manifests for errors without making changes
    
       Examples:
       kubecuro scan .                    # Pretty table output
       kubecuro scan . -o json            # JSON for automation  
       kubecuro scan . --diff             # Show suggested fixes
    
    """
    run_processing_loop(path, dry_run=True, diff=diff, max_depth=max_depth, ext=ext, strict=strict, output=output)

@cli.command(help="Apply logical healing and fix manifest errors")
@click.help_option("-h", "--help", help="Show detailed command help")
@click.argument("path", type=click.Path(exists=True))
# Core Options (Top priority - most used)
@click.option("--output", "-o", type=click.Choice(['table', 'json']), default='table', 
              help="Output format (default: table)")
@click.option("--dry-run", is_flag=True, help="Preview changes without writing")
@click.option("--diff", is_flag=True, help="Show before/after side-by-side previews")
# Safety Controls (User protection)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation for single file")
@click.option("--yes-all", is_flag=True, help="Skip ALL safety checks - PRODUCTION RISK")
@click.option("--force", is_flag=True, help="Write even partial/incomplete heals")
# Scan Control (Advanced)
@click.option("--max-depth", type=int, default=10, 
              help="Max folder recursion depth (default: 10)")
@click.option("--ext", default=".yaml,.yml", 
              help="File extensions (default: .yaml,.yml)")
@click.option("--strict", is_flag=True, help="Fail on unknown fields")
def fix(path, dry_run, diff, yes, yes_all, force, max_depth, ext, strict, output):
    """Auto-heal Kubernetes manifests with safety gates
    
    Examples:
        kubecuro fix .                    # Interactive healing
        kubecuro fix . --dry-run          # Safe preview
        kubecuro fix deployment.yaml -y   # Single file, no prompt
        kubecuro fix . -o json --yes-all  # Batch automation
    """
    run_processing_loop(path, dry_run, diff, max_depth, ext, strict, force, yes, yes_all, output)

# --- CORE LOGIC ORCHESTRATOR ---

def run_processing_loop(path, dry_run, diff, max_depth, ext, strict, force=False, yes=False, yes_all=False, output='table'):
    """
    Core loop for manifest processing. Handles discovery and batch safety confirmations.
    """
    input_path = Path(path).resolve()
    workspace = input_path if input_path.is_dir() else input_path.parent
    
    # Catalog Discovery Logic
    if hasattr(sys, '_MEIPASS'):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent

    search_locations = [
        base_path / "catalog" / "k8s_v1_distilled.json",
        Path("catalog/k8s_v1_distilled.json") # Local development fallback
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
        extensions = [e.lstrip('.') for e in ext.split(',')]
        target_files = []
        for e in extensions:
            target_files.extend([f for f in input_path.rglob(f"*.{e}") if f.is_file() and not f.is_symlink()])
        target_files = sorted(list(set(target_files)))

    if not target_files:
        console.print(f"\n[bold yellow]⚠️  No valid {ext} manifests found.[/bold yellow]")
        return

    # Safety Gate: Bulk confirmation
    if not dry_run:
        if len(target_files) > 1 and not yes_all:
            console.print(Panel(
                f"[bold red]⚠️  SAFETY GATE: BULK FIX ({len(target_files)} manifests)[/bold red]\n\n"
                f"[yellow]⚠️   Use `kubecuro fix . --dry-run --diff` FIRST to preview changes[/yellow]\n"
                f"[white]Target: {path}[/white]\n\n"
                f"[bold cyan]🚀 CONFIRM to auto-heal ALL manifests[/bold cyan]",
                expand=False, border_style="red"
            ))
            
            response = console.input("[bold yellow]Type 'CONFIRM' to proceed: [/bold yellow]").strip().upper()
            if response != "CONFIRM":
                console.print("[bold red]✓ Aborted safely[/bold red]")
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
        transient=True 
    ) as progress:
        task = progress.add_task("[cyan]Analyzing manifests...", total=len(target_files))
        
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

        progress.update(task, completed=len(target_files), description="[bold green]✓ Analysis complete[/bold green]")
    
    if output == 'json':
        import json
        console.print(json.dumps(reports, indent=2))
        return  # Skip table output, exit early

    render_summary(reports, engine)

def render_summary(reports: List[Dict], engine: Any):
    """
    Constructs final execution tables, git safety warnings, and summary panels.
    """
    table = Table(
        title="\n[bold magenta]KubeCuro Execution Report[/bold magenta]", 
        show_lines=True, 
        header_style="bold",
        box=box.MINIMAL_HEAVY_HEAD,
        expand=False
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
    console.print(Panel(summary_text, border_style="cyan", expand=False))

if __name__ == "__main__":
    #print_header()
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[bold red]Operation terminated by user.[/bold red]")
        sys.exit(1)
