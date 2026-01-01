# Dog Commands - Quick Reference

## PRODUCTION TOOLS - Visibility & Monitoring

### dog-cli.sh - Unified CLI (NEW - Production Ready)
Unified interface for all common Dog operations.

```bash
# Quick status check
./dog-cli.sh status                 # Show latest 2 workflows

# History and details
./dog-cli.sh history                # Show last 10 runs
./dog-cli.sh history 5              # Show last 5 runs
./dog-cli.sh history 10 latest      # Show details for latest run
./dog-cli.sh history 10 20251231-125718  # Show details for specific run

# Logs
./dog-cli.sh logs                   # Show logs from latest run
./dog-cli.sh logs 20251231-125718   # Show logs from specific run

# List all runs
./dog-cli.sh list                   # Show all runs (numbered summary)

# Run a workflow
./dog-cli.sh run my-workflow.yaml

# Cleanup old runs
./dog-cli.sh clean 20               # Keep only last 20 runs

# Help
./dog-cli.sh help
```

### dog-status.sh - Quick Status (Production Ready)
Shows the last 2 workflows at a glance (latest + previous).

```bash
./dog-status.sh
```

Output shows: Status (✓/✗), completion count, duration, timestamps.

### dog-history.sh - Full History (Production Ready)
Shows workflow history with optional detailed view.

```bash
# Show last 10 runs
./dog-history.sh 10

# Show last 5 runs
./dog-history.sh 5

# Show detailed info for latest run
./dog-history.sh 10 latest

# Show detailed info for specific run
./dog-history.sh 10 20251231-125718
```

Detailed view includes: metadata, summary, logs, agent output.

**See:** PRODUCTION_GUIDE.md for comprehensive documentation of visibility tools.

---

## Главные скрипты

### dog.py - Запуск workflow
```bash
# Запустить workflow
python3 dog.py workflow.yaml

# Возобновить workflow (если был завершен/прерван)
python3 dog.py --resume 20251230-165505

# Запустить в paused режиме (потом можешь управлять)
python3 dog.py --pause workflow.yaml
```

### dog-workflows.sh - Список всех workflow'ов
```bash
# Показать все активные workflow'ы (с номерами!)
./dog-workflows.sh

# Показать детали конкретного workflow'а:
./dog-workflows.sh 1               # По номеру из списка
# или
./dog-workflows.sh 20251230-165505  # По GUID

# Real-time мониторинг (обновляется каждые 2 сек)
watch -n 2 './dog-workflows.sh'
```

### dog-cmd.sh - Управление процессами
```bash
# Показать статус (если один workflow, auto-detect)
./dog-cmd.sh status

# Показать список процессов
./dog-cmd.sh list

# Если несколько workflow'ов, можно указать номер или GUID:
./dog-cmd.sh 2 status             # По номеру из ./dog-workflows.sh
./dog-cmd.sh 2 list

# Или по GUID
./dog-cmd.sh 20251230-165505 status
./dog-cmd.sh 20251230-165505 list

# Управление процессом (с номером)
./dog-cmd.sh 2 pause task-1        # Поставить на паузу
./dog-cmd.sh 2 resume task-1       # Возобновить
./dog-cmd.sh 2 cancel task-1       # Убить процесс

# Управление процессом (с GUID)
./dog-cmd.sh 20251230-165505 pause agent-1-step-2
./dog-cmd.sh 20251230-165505 resume agent-1-step-2
./dog-cmd.sh 20251230-165505 cancel agent-1-step-2
```

## Логи и мониторинг

### Посмотреть логи (вместо dog-cmd list)
```bash
# Последние логи
tail -20 /tmp/dog-runs/run-20251230-165505/dog.log

# Real-time логи
tail -f /tmp/dog-runs/run-20251230-165505/dog.log

# Поиск по статусу
grep "PROCESS STARTED" /tmp/dog-runs/run-20251230-165505/dog.log
grep "PROCESS COMPLETED" /tmp/dog-runs/run-20251230-165505/dog.log
grep "PROCESS FAILED" /tmp/dog-runs/run-20251230-165505/dog.log

# Подсчитать
grep "PROCESS COMPLETED" /tmp/dog-runs/run-20251230-165505/dog.log | wc -l
grep "PROCESS FAILED" /tmp/dog-runs/run-20251230-165505/dog.log | wc -l
```

### Посмотреть процессы системы
```bash
# Активные Dog процессы
ps aux | grep dog.py | grep -v grep

# Активные Claude processes (агенты)
ps aux | grep claude | head -20

# Активные процессы из workflow'а
ps aux | grep "task-1\|task-2" | grep -v grep
```

## Workflow GUID

GUID это timestamp: `YYYYMMDD-HHMMSS`

Примеры:
- `20251230-165505` = 2025-12-30 16:55:05
- `20251230-150455` = 2025-12-30 15:04:55

Узнать GUID текущего workflow'а:
```bash
# Последний workflow
ls -td /tmp/dog-runs/run-* | head -1 | xargs basename
# Output: run-20251230-165505

# Извлечь просто GUID
ls -td /tmp/dog-runs/run-* | head -1 | xargs basename | sed 's/run-//'
```

## Socket API (низкоуровневый)

Если нужна прямая работа с socket'ом:

```bash
# Отправить команду напрямую
echo "status" | nc -U /tmp/dog-20251230-165505.sock

echo "pause task-1" | nc -U /tmp/dog-20251230-165505.sock

echo "resume task-1" | nc -U /tmp/dog-20251230-165505.sock

echo "list" | nc -U /tmp/dog-20251230-165505.sock
```

## Часто используемые комбинации

### Полный цикл: создание, запуск, управление
```bash
# 1. Создать workflow YAML
cat > my-workflow.yaml << 'EOFYAML'
semaphore: 3
timeout: 120
blocks:
  - name: task-1
    command: "sleep 10"
  - name: task-2
    command: "sleep 10"
EOFYAML

# 2. Запустить (в background)
python3 dog.py my-workflow.yaml &

# 3. Подождать немного (до запуска)
sleep 2

# 4. Посмотреть статус
./dog-workflows.sh

# 5. Управлять
./dog-cmd.sh pause task-1
./dog-cmd.sh resume task-1

# 6. Мониторить
watch -n 1 './dog-workflows.sh'
```

### Мониторить долгий workflow в реальном времени
```bash
# Терминал 1: запущен workflow
python3 dog.py large-workflow.yaml

# Терминал 2: мониторинг
watch -n 2 './dog-workflows.sh'

# Терминал 3: детальные логи
tail -f /tmp/dog-runs/run-*/dog.log | grep "PROCESS"
```

### Контролировать из bash скрипта
```bash
#!/bin/bash

# Получить GUID последнего workflow'а
GUID=$(ls -td /tmp/dog-runs/run-* | head -1 | xargs basename | sed 's/run-//')

echo "Controlling workflow: $GUID"

# Pausить все task-а с "agent-1"
grep "agent-1" /tmp/dog-runs/run-$GUID/dog.log | grep "STARTED" | \
  grep -o "agent-1[^ ]*" | while read task; do
    ./dog-cmd.sh $GUID pause "$task"
  done

# Или просто
sleep 30
./dog-cmd.sh $GUID status
```

## Обычные проблемы

| Проблема | Решение |
|----------|---------|
| `dog-cmd.sh list` пусто | Посмотри лог: `tail /tmp/dog-runs/run-GUID/dog.log \| grep PROCESS` |
| Multiple workflows detected | Укажи GUID: `./dog-cmd.sh GUID status` |
| Command unknown | Проверь синтаксис: `pause task-1` не `pause=task-1` |
| Socket connection refused | Workflow не запущен или зависла. Проверь: `ps aux \| grep dog.py` |
| No socket found | Неправильный GUID. Узнай: `./dog-workflows.sh` |

## Структура директорий

```
/server/scripts/agent-pm2-dog/
├── dog.py                        # Main workflow engine
├── dog-cmd.sh                    # Command control (pause/resume/cancel)
├── dog-workflows.sh              # List/monitor workflows
├── mock-agent.py                 # Example agent for testing
├── generate-100-tasks.py         # Generator for large tests
├── README.md                      # Full documentation (this file)
├── COMMANDS.md                    # Command reference (this file)
├── test-100-tasks.yaml           # Example: 111 task configuration
├── test-pipeline.yaml            # Example: 3-agent pipeline
├── dog-deliberation-config.yaml  # Example: team-deliberation workflow

/tmp/dog-runs/
└── run-YYYYMMDD-HHMMSS/
    ├── dog.log                   # Main log (всё что происходит)
    ├── dog.db                    # SQLite database (состояние)
    └── logs/                     # Individual process logs
```

## Help/Usage

Встроенная помощь:
```bash
python3 dog.py -h
```
