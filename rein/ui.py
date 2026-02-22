"""
Rein UI - htop-like terminal UI using rich library
"""
import os
import time
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.live import Live

if TYPE_CHECKING:
    from rein.orchestrator import ProcessManager


class ReinUI:
    """htop-like terminal UI using rich"""

    def __init__(self, manager: "ProcessManager"):
        self.manager = manager
        self.console = Console()

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes as human-readable: 1.2K, 3.4M, etc."""
        if size_bytes == 0:
            return "0"
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}K"
        else:
            return f"{size_bytes / (1024 * 1024):.1f}M"

    def _get_block_flags(self, block_name: str) -> str:
        """Get compact flags string for block: P D2 L N S C R3"""
        block = self.manager.block_configs.get(block_name, {})
        flags = []

        # P = parallel
        if block.get('parallel', False):
            flags.append("P")

        # D{n} = depends_on count
        deps = block.get('depends_on', [])
        if deps:
            flags.append(f"D{len(deps)}")

        # L = has logic scripts
        logic = block.get('logic', {})
        if logic and any(logic.get(k) for k in ['pre', 'post', 'validate', 'custom']):
            flags.append("L")

        # N = has next (conditional jump)
        if block.get('next'):
            flags.append("N")

        # S = skip_if_previous_failed
        if block.get('skip_if_previous_failed', False):
            flags.append("S")

        # C = continue_if_failed
        if block.get('continue_if_failed', False):
            flags.append("C")

        # R{n} = max_runs (loop)
        max_runs = block.get('max_runs', 1)
        if max_runs > 1:
            flags.append(f"R{max_runs}")

        return " ".join(flags) if flags else "-"

    def _get_io_sizes(self, block_name: str, proc_status: str) -> str:
        """Get IN/OUT sizes: '1.2K/0.8K' or '-/-' if not ready"""
        if proc_status == "waiting":
            return "-/-"

        task_dir = self.manager.task_dir
        if not task_dir:
            return "-/-"

        # Calculate IN size (sum of dependency outputs)
        block = self.manager.block_configs.get(block_name, {})
        deps = block.get('depends_on', [])
        in_size = 0
        for dep in deps:
            dep_path = os.path.join(task_dir, dep, 'outputs', 'result.json')
            if os.path.exists(dep_path):
                in_size += os.path.getsize(dep_path)

        # Calculate OUT size
        out_path = os.path.join(task_dir, block_name, 'outputs', 'result.json')
        out_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0

        in_str = self._format_size(in_size)
        out_str = self._format_size(out_size) if out_size > 0 else "-"

        return f"{in_str}/{out_str}"

    def calculate_overall_progress(self) -> tuple:
        """Calculate overall progress: (completed_count, total_count, percent)"""
        processes = self.manager.state.get_all_processes()
        if not processes:
            return 0, 0, 0

        total = len(processes)
        completed = sum(1 for p in processes if p.status in ("done", "failed"))

        # Also account for progress of running processes
        running_processes = [p for p in processes if p.status == "running"]
        running_count = len(running_processes)
        running_progress = sum(p.progress for p in running_processes) / max(1, running_count) if running_count > 0 else 0

        # Overall percent = (completed agents * 100 + running agents * their progress) / total
        overall_percent = ((completed * 100) + (running_count * running_progress)) / total

        return completed, total, int(overall_percent)

    def get_time_info(self) -> str:
        """Get elapsed and remaining time"""
        if not self.manager.metadata.get("start_time"):
            return ""

        from datetime import datetime
        start_time = datetime.fromisoformat(self.manager.metadata["start_time"])
        elapsed = int((datetime.now() - start_time).total_seconds())

        # Format elapsed
        elapsed_str = f"{elapsed}s"

        # Calculate remaining if timeout is set
        if self.manager.timeout:
            remaining = max(0, self.manager.timeout - elapsed)
            if remaining > 0:
                remaining_str = f" | [TIMER] {remaining}s remaining"
            else:
                remaining_str = " | [TIMER] TIMEOUT!"
            return f"[TIME] {elapsed_str}{remaining_str}"
        else:
            return f"[TIME] {elapsed_str}"

    def _get_task_summary(self, max_len: int = 500) -> str:
        """Get task description for UI header"""
        task_text = ""
        # Try task_input.topic first, then task_input.task
        if self.manager.task_input:
            task_text = self.manager.task_input.get('topic', '')
            if not task_text:
                task_text = self.manager.task_input.get('task', '')
        # Clean and truncate if needed
        if task_text:
            # Strip markdown headers, normalize whitespace
            text = task_text.strip().lstrip('#').strip()
            # Replace newlines with spaces for single-line display
            text = ' '.join(text.split())
            if len(text) > max_len:
                text = text[:max_len-3] + "..."
            return text
        return ""

    def render_table(self) -> Table:
        """Render process table with overall progress"""
        completed, total, percent = self.calculate_overall_progress()
        time_info = self.get_time_info()

        # Create progress bar
        bar_length = 20
        filled = int(bar_length * percent / 100)
        bar = "=" * filled + "-" * (bar_length - filled)
        progress_str = f"[bold blue]{bar}[/bold blue] {percent}% ({completed}/{total})"

        # Add workflow paused indicator if applicable
        workflow_status = " | [red][WORKFLOW PAUSED][/red]" if self.manager.workflow_paused else ""

        # Get task summary for header
        task_summary = self._get_task_summary()
        task_line = f"\n[bold white]{task_summary}[/bold white]" if task_summary else ""

        # Create main table with time info and legend
        title = f"Rein - Workflow Monitor - Overall: {progress_str} | {time_info}{workflow_status}{task_line}\n[dim]Flags: P=parallel D=deps L=logic N=next S=skip C=continue R=max_runs[/dim]"
        table = Table(title=title, show_header=True)
        table.add_column("Name", style="magenta", width=16)
        table.add_column("Status", style="green", width=8)
        table.add_column("Flags", style="dim", width=12)
        table.add_column("IN/OUT", style="cyan", width=10)
        table.add_column("Progress", style="blue", width=14)
        table.add_column("Time", style="blue", width=5)

        processes = self.manager.state.get_all_processes()
        for proc in processes:
            if proc.start_time:
                elapsed = time.time() - proc.start_time
            else:
                elapsed = 0

            # Style status based on state
            status_styles = {
                "running": "[yellow]running[/yellow]",
                "done": "[green]done[/green]",
                "failed": "[red]failed[/red]",
                "waiting": "[dim]waiting[/dim]",
                "paused": "[cyan][PAUSED][/cyan]"
            }
            status_text = status_styles.get(proc.status, proc.status)

            # Create ASCII progress bar (only for non-waiting/non-paused processes)
            if proc.status in ("waiting", "paused"):
                progress_str = "-"
                time_str = "-"
            else:
                progress = proc.progress
                bar_length = 8
                filled = int(bar_length * progress / 100)
                bar = "=" * filled + "-" * (bar_length - filled)
                progress_str = f"{bar} {progress}%"
                time_str = f"{elapsed:.0f}s"

            # Get flags and IO sizes
            flags_str = self._get_block_flags(proc.name)
            io_str = self._get_io_sizes(proc.name, proc.status)

            table.add_row(
                proc.name,
                status_text,
                flags_str,
                io_str,
                progress_str,
                time_str
            )

        return table

    def run_live(self):
        """Run live monitoring"""
        with Live(self.render_table(), console=self.console, refresh_per_second=4) as live:
            try:
                while self.manager.running:
                    live.update(self.render_table())
                    time.sleep(0.25)
                # Final render to show completed state
                time.sleep(0.3)
                live.update(self.render_table())
            except KeyboardInterrupt:
                self.console.print("\n[red]Stopped[/red]")
                self.manager.running = False
