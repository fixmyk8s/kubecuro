# src/kubecuro/cli/formatter.py
import difflib
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

# Initialize the Rich console for high-quality terminal output
console = Console()

class KubeFormatter:
    """
    KubeFormatter: The visual heart of the CLI.
    Responsible for rendering Diffs, Logic Warnings, and Execution Reports.
    """

    def display_diff(self, original_text: str, healed_text: str, file_name: str):
        """
        Calculates and renders a colorized diff between the original 
        corrupted YAML and the Shield-hardened output.
        """
        # Ensure we have content to compare to avoid crashes
        if not healed_text or not original_text:
            return

        # Generate a Unified Diff (standard format for line changes)
        diff = difflib.unified_diff(
            original_text.splitlines(),
            healed_text.splitlines(),
            fromfile=f"Original: {file_name}",
            tofile=f"Healed Version",
            lineterm=""
        )

        diff_list = list(diff)
        
        if not diff_list:
            console.print(f"[dim]ℹ No structural or logical changes needed for {file_name}.[/dim]")
            return

        # Combine diff lines and wrap in a Rich Panel for clear UI separation
        diff_output = "\n".join(diff_list)
        syntax = Syntax(diff_output, "diff", theme="monokai", line_numbers=True)
        
        console.print(Panel(
            syntax, 
            title=f"Proposed Healing: {file_name}", 
            subtitle="ER Pass Complete", 
            border_style="green"
        ))

    def show_shield_logs(self, logs: list):
        """
        Iterates through the logic logs from the ShieldEngine 
        to explain WHY changes (like limits) were injected.
        """
        if not logs:
            return

        for log in logs:
            # Using bold cyan to distinguish logic warnings from structural fixes
            console.print(f"[bold cyan]🛡  Shield Policy Applied:[/bold cyan] {log}")

    def print_final_table(self, reports: list):
        """
        Builds the summary table shown at the very end of a scan.
        """
        table = Table(title="KubeCuro Execution Report", show_header=True, header_style="bold magenta")
        table.add_column("File Path", style="dim")
        table.add_column("Kind")
        table.add_column("Status")
        table.add_column("Result", justify="center")

        for r in reports:
            # Choose icons based on success
            result_icon = "✅" if r.get("success") else "❌"
            table.add_row(
                r.get("file_path"),
                r.get("kind"),
                r.get("status"),
                result_icon
            )
        
        console.print(table)
