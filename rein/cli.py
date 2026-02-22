"""
Rein CLI - Command-line interface and argument parsing.

Installed as the `rein` command via pip:
    pip install rein-ai
    rein workflow.yaml
    rein --flow deliberation --question task.txt
    rein --daemon
"""
import os
import sys
import json
import yaml
import time
import signal
import threading
import argparse

from rein.config import DEFAULT_AGENTS_DIR
from rein.state import ReinState


def main():
    """Entry point for the `rein` CLI command."""

    from rein import __version__
    parser = argparse.ArgumentParser(description='Rein - Workflow Orchestrator')
    parser.add_argument('--version', '-V', action='version', version=f'rein {__version__}')
    parser.add_argument('config', nargs='?', help='Path to YAML configuration file (or use --flow/--task)')
    parser.add_argument('--flow', metavar='FLOW_NAME', help='Flow name (creates new task automatically)')
    parser.add_argument('--input', metavar='JSON', help='Input parameters as JSON (used with --flow)')
    parser.add_argument('--task-dir', metavar='DIR', help='Task directory with task.md (used with --flow)')
    parser.add_argument('--question', metavar='FILE', help='Question file path (simple question without task dir)')
    parser.add_argument('--task', metavar='TASK_DIR', help='Task directory (e.g., /path/to/tasks/task-001)')
    parser.add_argument('--status', metavar='TASK_ID', help='Show task status')
    parser.add_argument('--pause', action='store_true', help='Start workflow in paused state')
    parser.add_argument('--resume', metavar='RUN_ID', help='Resume from previous run (RUN_ID like 20251230-142345)')
    parser.add_argument('--no-ui', action='store_true', help='Run without Rich UI (for scripts/non-terminals)')
    parser.add_argument('--agents-dir', metavar='PATH', default=DEFAULT_AGENTS_DIR,
                        help=f'Agents directory (specialists, teams, flows, tasks). Default: {DEFAULT_AGENTS_DIR}')
    parser.add_argument('--daemon', action='store_true',
                        help='Run as daemon, watching for pending tasks')
    parser.add_argument('--daemon-interval', type=int, default=5,
                        help='Daemon check interval in seconds (default: 5)')
    parser.add_argument('--max-workflows', type=int, default=3,
                        help='Maximum parallel workflows in daemon mode (default: 3)')
    parser.add_argument('--ws-port', type=int, default=8765,
                        help='WebSocket server port for live updates (default: 8765)')
    parser.add_argument('--run-task', metavar='TASK_ID',
                        help='Execute specific task (used internally by daemon)')

    args = parser.parse_args()

    # Handle --run-task mode (subprocess spawned by daemon)
    if args.run_task:
        from rein.tasks import execute_task
        exit_code = execute_task(args.run_task, args.agents_dir)
        sys.exit(exit_code)

    # Handle --daemon mode
    if args.daemon:
        from rein.daemon import run_daemon
        run_daemon(args.agents_dir, args.daemon_interval, args.max_workflows, args.ws_port, args.no_ui)
        sys.exit(0)

    # Handle --status command
    if args.status:
        _handle_status(args)
        sys.exit(0)

    # Handle --flow mode
    if args.flow:
        manager = _handle_flow(args)

    # Handle --task mode
    elif args.task:
        manager = _handle_task(args)

    # Handle config file mode
    elif args.config:
        manager = _handle_config(args)

    else:
        print("[ERROR] Provide config file, --flow, or --task")
        parser.print_help()
        sys.exit(1)

    # Pause workflow if --pause flag provided
    if args.pause:
        manager.pause_workflow()
        print("[PAUSE] Workflow started in paused state")

    # Print run info
    print(f"\n[DIR] Run Directory: {manager.run_dir}")
    print(f"[DB] Database: {manager.db_path}")
    print(f"[LOGS] Logs: {manager.log_dir}")
    if 'start_time' in manager.metadata:
        print(f"[TIMER] Start Time: {manager.metadata['start_time']}")
    elif 'resumed_at' in manager.metadata:
        print(f"[TIMER] Resumed At: {manager.metadata['resumed_at']}")
    if manager.timeout:
        print(f"[TIMEOUT] Timeout: {manager.timeout}s")
    if args.resume:
        print(f"[RESUME] Continuing from run: {args.resume}")
    print()

    # Setup graceful shutdown handler
    def signal_handler(signum, frame):
        print("\n\n[SHUTDOWN] Graceful shutdown initiated...")
        manager._write_rein_log("SIGINT RECEIVED | graceful shutdown")
        manager._kill_remaining_processes("user interrupt")
        manager.running = False
        time.sleep(2)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Start stdin reader for pause/resume commands
    manager.start_stdin_reader()

    # Start Unix domain socket server for async commands
    manager.start_socket_server()

    # Run workflow
    if args.no_ui:
        manager.run_workflow()
    else:
        from rein.ui import ReinUI
        workflow_thread = threading.Thread(target=manager.run_workflow, daemon=True)
        workflow_thread.start()
        ui = ReinUI(manager)
        ui.run_live()

    # Print final result after UI exits (clean stdout)
    manager._print_final_result()

    manager.running = False
    sys.exit(0)


def _handle_status(args):
    """Handle --status command: show task status and outputs."""
    agents_dir = args.agents_dir
    tasks_root = os.path.join(agents_dir, "tasks")
    task_dir = os.path.join(tasks_root, args.status)
    task_json_path = os.path.join(task_dir, "input", "task.json")
    status_path = os.path.join(task_dir, "state", "status")

    if not os.path.exists(task_dir):
        print(f"[ERROR] Task not found: {args.status}")
        sys.exit(1)

    if os.path.exists(task_json_path):
        with open(task_json_path) as f:
            task_data = json.load(f)
        print(f"\n[TASK] ID: {task_data.get('id')}")
        print(f"[TASK] Flow: {task_data.get('flow')}")
        print(f"[TASK] Created: {task_data.get('created')}")
        print(f"[TASK] Status: {task_data.get('status')}")
        if task_data.get('input'):
            print(f"[TASK] Input: {json.dumps(task_data.get('input'), ensure_ascii=False)}")

    if os.path.exists(status_path):
        with open(status_path) as f:
            print(f"[STATUS] {f.read().strip()}")

    outputs_dir = os.path.join(task_dir, "outputs")
    if os.path.exists(outputs_dir):
        outputs = os.listdir(outputs_dir)
        if outputs:
            print(f"\n[OUTPUTS] {len(outputs)} files:")
            for f in sorted(outputs):
                fpath = os.path.join(outputs_dir, f)
                size = os.path.getsize(fpath)
                print(f"  - {f} ({size} bytes)")
    print()


def _handle_flow(args):
    """Handle --flow mode: create task and run flow."""
    from rein.orchestrator import ProcessManager
    from rein.tasks import load_config

    flow_name = args.flow
    agents_dir = args.agents_dir
    flow_path = os.path.join(agents_dir, 'flows', flow_name, f'{flow_name}.yaml')

    if not os.path.exists(flow_path):
        print(f"[ERROR] Flow not found: {flow_path}")
        sys.exit(1)

    # Parse input: --question, --task-dir or --input
    question_file = args.question
    task_dir_provided = args.task_dir
    task_input = {}

    if question_file:
        if not os.path.exists(question_file):
            print(f"[ERROR] Question file not found: {question_file}")
            sys.exit(1)
        with open(question_file, 'r') as f:
            task_content = f.read()
        task_input = {"task": task_content}
        context_dir = os.path.join(os.path.dirname(os.path.abspath(question_file)), 'context')
        if os.path.isdir(context_dir):
            task_content += f"\n\nContext files available in: {context_dir}"
            task_input = {"task": task_content}
    elif task_dir_provided:
        task_md_path = os.path.join(task_dir_provided, 'task.md')
        if not os.path.exists(task_md_path):
            print(f"[ERROR] task.md not found in: {task_dir_provided}")
            sys.exit(1)
        with open(task_md_path, 'r') as f:
            task_content = f.read()
        task_input = {"task": task_content}
    elif args.input:
        try:
            task_input = json.loads(args.input)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON input: {e}")
            sys.exit(1)

    config = load_config(flow_path)

    manager = ProcessManager(
        max_parallel=config.get('semaphore', 3),
        flow_name=flow_name,
        task_input=task_input,
        agents_dir=agents_dir
    )

    if task_dir_provided:
        task_dir_provided = task_dir_provided.rstrip('/')
        task_id = os.path.basename(task_dir_provided)
        manager.task_id = task_id
        manager.task_dir = task_dir_provided
        os.makedirs(os.path.join(task_dir_provided, "outputs"), exist_ok=True)
    else:
        task_id = manager.create_task(flow_name, task_input)
        manager.task_id = task_id
        manager.task_dir = os.path.join(manager.tasks_root, task_id)

    manager.run_dir = manager.task_dir
    manager.log_dir = os.path.join(manager.task_dir, "state")
    manager.rein_log_file = os.path.join(manager.task_dir, "state", "rein.log")
    manager.db_path = os.path.join(manager.task_dir, "state", "rein.db")
    os.makedirs(manager.log_dir, exist_ok=True)
    manager.state = ReinState(manager.db_path, resume=False)

    manager.load_config(config, workflow_file=flow_path)

    print(f"\n[TASK] ID: {task_id}")
    print(f"[TASK] Flow: {flow_name}")
    print(f"[TASK] Directory: {manager.task_dir}")
    if task_input and task_input.get('task'):
        task_preview = task_input['task'][:100] + "..." if len(task_input.get('task', '')) > 100 else task_input.get('task', '')
        print(f"[TASK] Input: {task_preview}")

    return manager


def _handle_task(args):
    """Handle --task mode: load flow from task.yaml."""
    from rein.orchestrator import ProcessManager
    from rein.tasks import load_config

    task_dir = args.task.rstrip('/')
    task_yaml_path = os.path.join(task_dir, 'task.yaml')

    if not os.path.exists(task_yaml_path):
        print(f"[ERROR] Task file not found: {task_yaml_path}")
        sys.exit(1)

    with open(task_yaml_path) as f:
        task_config = yaml.safe_load(f)

    flow_name = task_config.get('flow')
    if not flow_name:
        print("[ERROR] Task must specify 'flow' field")
        sys.exit(1)

    agents_dir = args.agents_dir
    flow_path = os.path.join(agents_dir, 'flows', flow_name, f'{flow_name}.yaml')
    if not os.path.exists(flow_path):
        print(f"[ERROR] Flow not found: {flow_path}")
        sys.exit(1)

    config = load_config(flow_path)

    output_dir = task_config.get('output_dir', './outputs')
    output_dir = os.path.join(task_dir, output_dir.lstrip('./'))
    config['output_dir'] = output_dir
    config['task_dir'] = task_dir
    config['task_config'] = task_config

    manager = ProcessManager(
        max_parallel=config.get('semaphore', 3),
        task_id=os.path.basename(task_dir),
        flow_name=flow_name,
        task_input=task_config.get('input', {}),
        agents_dir=agents_dir
    )
    manager.task_dir = task_dir
    manager.run_dir = task_dir
    manager.load_config(config, workflow_file=flow_path)

    print(f"\n[TASK] ID: {task_config.get('id')}")
    print(f"[TASK] Flow: {flow_name}")
    print(f"[TASK] Output: {output_dir}\n")

    return manager


def _handle_config(args):
    """Handle config file mode: run workflow from YAML file."""
    from rein.orchestrator import ProcessManager
    from rein.tasks import load_config

    config = load_config(args.config)
    agents_dir = args.agents_dir

    task_input = {}
    if args.input:
        try:
            task_input = json.loads(args.input)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON input: {e}")
            sys.exit(1)

    manager = ProcessManager(
        max_parallel=config.get('semaphore', 3),
        resume_run_id=args.resume,
        agents_dir=agents_dir,
        task_input=task_input
    )
    manager.load_config(config, workflow_file=args.config)

    return manager


if __name__ == "__main__":
    main()
