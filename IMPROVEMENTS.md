# Dog - User Experience Improvements

**Date:** 2025-12-30
**Issue:** "Как посмотреть список процессов workflow'а? И почему куча скриптов без справки?"

## Что было улучшено

### 1. Нумерация workflow'ов в ./dog-workflows.sh

**Было:**
```bash
./dog-workflows.sh                    # Показывает список
./dog-workflows.sh 20251230-165505    # Нужно помнить полный GUID!
```

**Теперь:**
```bash
./dog-workflows.sh
# Output:
#  [1] 20251230-145533 Progress: 100% ...
#  [2] 20251230-150455 Progress: 100% ...
#  
# To see details: ./dog-workflows.sh <N>

./dog-workflows.sh 1    # Просто по номеру!
./dog-workflows.sh 2
```

### 2. Нумерация в ./dog-cmd.sh

**Было:**
```bash
./dog-cmd.sh 20251230-165505 pause task-1   # Нужен полный GUID
```

**Теперь:**
```bash
./dog-cmd.sh 2 pause task-1    # По номеру из списка
# или
./dog-cmd.sh 20251230-165505 pause task-1   # Старый способ тоже работает
```

### 3. Полная документация

Создана нормальная справка:

| Файл | Назначение |
|------|-----------|
| **README.md** | Полная документация с примерами (Quick Start, YAML, архитектура) |
| **COMMANDS.md** | Быстрая справка на русском (все команды с примерами) |
| **IMPROVEMENTS.md** | Этот файл (что было улучшено) |

## Примеры использования

### Простой workflow (один процесс)
```bash
# 1. Запустить
python3 dog.py simple.yaml

# 2. Мониторить (в другом терминале)
./dog-workflows.sh        # Посмотреть статус

# 3. Управлять
./dog-cmd.sh pause task-1         # Auto-detect (один workflow)
./dog-cmd.sh resume task-1
```

### Несколько workflow'ов одновременно
```bash
# Terminal 1
python3 dog.py workflow-1.yaml

# Terminal 2
python3 dog.py workflow-2.yaml

# Terminal 3
./dog-workflows.sh
# Output:
# [1] 20251230-165505 ... 
# [2] 20251230-165510 ...

./dog-cmd.sh 1 status      # Статус workflow #1
./dog-cmd.sh 2 status      # Статус workflow #2

./dog-cmd.sh 1 pause task-1    # Pause в workflow #1
./dog-cmd.sh 2 pause task-2    # Pause в workflow #2
```

### Долгий мониторинг
```bash
# Terminal 1: запущен workflow
python3 dog.py large-workflow.yaml

# Terminal 2: real-time мониторинг (обновляется каждые 2 сек)
watch -n 2 './dog-workflows.sh'
```

## Что дальше

**Проблема с `dog-cmd.sh list`:**

Команда `list` отправляется через socket и результат пишется в Dog's логи, не в stdout. Это нужно исправить в dog.py - добавить возможность вернуть результат обратно через socket.

**Временное решение:**
```bash
# Вместо
./dog-cmd.sh 1 list    # пусто

# Используй
tail /tmp/dog-runs/run-GUID/dog.log | grep "PROCESS"

# Или
./dog-workflows.sh 1   # Показывает детали
```

## Итого

✓ Нумерация workflow'ов для быстрого доступа  
✓ Нумерация в dog-cmd.sh для управления  
✓ Полная документация (README.md + COMMANDS.md)  
✓ Примеры для разных сценариев  

**Теперь можешь:**
- Быстро посмотреть список workflow'ов: `./dog-workflows.sh`
- Посмотреть детали: `./dog-workflows.sh 1` (по номеру!)
- Управлять: `./dog-cmd.sh 1 status` (по номеру!)
- Получить справку: `cat README.md` или `cat COMMANDS.md`
