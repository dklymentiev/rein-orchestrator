# Правила проектирования процессов Dog v2

**Версия:** 2.5.3
**Дата:** 2026-01-01

---

## Предисловие

Dog v2 - это мета-оркестратор для сложных рабочих процессов. Архитектура позволяет управлять потоком выполнения блоков через явные параметры контроля.

Эти правила помогут избежать проблем и создавать надёжные процессы.

---

## 1. Классификация блоков по важности

### Critical блоки (критичные)
- Failure блока **останавливает весь процесс**
- `continue_if_failed: false`
- Примеры: валидация входных данных, критичные проверки

### Optional блоки (опциональные)
- Failure блока **не влияет на остальной процесс**
- `continue_if_failed: true` (по умолчанию)
- Примеры: обогащение данных, логирование, резервные копии

### Resilient блоки (устойчивые)
- Выполняются **несмотря на ошибки ранее**
- `skip_if_previous_failed: true`
- Примеры: очистка ресурсов, уведомления, откат транзакций

---

## 2. Параметры контроля потока

### `continue_if_failed` (продолжать ли при ошибке?)

```yaml
# Критичный блок - стоп при ошибке
- name: data_validation
  specialist: validator
  continue_if_failed: false  # СТОП если валидация упадёт

# Опциональный блок - продолжи при ошибке
- name: send_notification
  specialist: notifier
  continue_if_failed: true   # Продолжи, даже если уведомление не отправилось
```

**Значение по умолчанию:** `true` (продолжить)

### `skip_if_previous_failed` (пропустить ли если были ошибки?)

```yaml
# Блок, требующий успеха предыдущих
- name: final_report
  specialist: reporter
  skip_if_previous_failed: false  # Пропусти если были ошибки ранее

# Блок, выполняемый всегда (даже при ошибках)
- name: cleanup
  specialist: cleanup
  skip_if_previous_failed: true   # Выполни, несмотря на ошибки ранее
```

**Значение по умолчанию:** `false` (пропустить при ошибках)

---

## 3. Комбинация параметров - матрица режимов

| continue_if_failed | skip_if_previous_failed | Поведение | Пример |
|---|---|---|---|
| false | false | CRITICAL: стоп при fail, пропусти при ошибках ранее | Валидация |
| false | true | Выполни всегда, но стоп при fail | Не рекомендуется |
| true | false | Выполни если нет ошибок ранее, продолжи при fail | Обработка данных |
| true | true | Выполни всегда, продолжи при fail | Очистка, логирование |

### Рекомендуемые комбинации

#### Валидация/проверки
```yaml
- name: input_validation
  specialist: validator
  continue_if_failed: false  # Стоп при ошибке
  # skip_if_previous_failed: false (по умолчанию) - не пропускай
```

#### Обработка данных
```yaml
- name: data_processing
  specialist: processor
  continue_if_failed: true   # Продолжи даже если обработка упадёт
  skip_if_previous_failed: false  # Пропусти если валидация упала
```

#### Очистка ресурсов
```yaml
- name: cleanup
  specialist: cleanup
  continue_if_failed: true   # Продолжи даже если очистка упадёт
  skip_if_previous_failed: true  # Выполни всегда, даже при ошибках ранее
```

#### Резервные копии
```yaml
- name: backup
  specialist: backup
  continue_if_failed: true   # Не стой если резервная копия упадёт
  skip_if_previous_failed: true  # Попытайся делать резервную копию несмотря на ошибки
```

---

## 4. Правила валидации

### Когда использовать валидацию (validate phase)

```python
# Валидируй ТОЛЬКО критичные ошибки структуры
if not isinstance(data, dict):
    raise ValueError("Expected dict")

if 'required_field' not in data:
    raise ValueError("Missing required_field")

# НЕ валидируй содержимое для random/stochastic данных
# НЕ валидируй красоту/качество (субъективно)
# НЕ валидируй опциональные поля
```

### Правильно
```yaml
- name: selection
  specialist: selector
  logic:
    post: select-theme.py  # Только обработка, БЕЗ validate
```

### Неправильно
```yaml
- name: selection
  specialist: selector
  logic:
    validate: validate-selection.py  # Validate для random данных?!
```

### JSON Schema для структуры

```python
# logic/validate-output.py
import json
import jsonschema

EXPECTED_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_item": {"type": "string"},
        "score": {"type": "number"}
    },
    "required": ["selected_item"]
}

def validate(data_file):
    with open(data_file) as f:
        envelope = json.load(f)

    result_str = envelope.get('result', '')
    data = json.loads(result_str)

    # Проверяем структуру
    jsonschema.validate(data, EXPECTED_SCHEMA)
    # Если валиден - скрипт завершится с кодом 0
    # Если невалиден - выбросит исключение, код 1
```

---

## 5. Параллельное выполнение и зависимости

### Параллельные блоки (одна фаза)

```yaml
blocks:
  - name: preparation
    specialist: prep
    # Первая фаза, нет зависимостей

  # Все три блока выполняются параллельно
  - name: task_1
    specialist: worker1
    depends_on: [preparation]
    parallel: true

  - name: task_2
    specialist: worker2
    depends_on: [preparation]
    parallel: true

  - name: task_3
    specialist: worker3
    depends_on: [preparation]
    parallel: true

  - name: aggregation
    specialist: aggregator
    depends_on: [task_1, task_2, task_3]  # Дождись всех трёх
```

### skip_if_previous_failed с параллелизмом

```yaml
blocks:
  - name: ideation
    specialist: ideator

  - name: selection
    specialist: selector
    skip_if_previous_failed: false
    continue_if_failed: true  # Failure selection не блокирует poets

  # Все три поэта выполняются параллельно
  - name: creation_1
    specialist: poet
    skip_if_previous_failed: true  # Игнорируй selection failure
    parallel: true

  - name: creation_2
    specialist: poet
    skip_if_previous_failed: true  # Игнорируй selection failure
    parallel: true

  - name: creation_3
    specialist: poet
    skip_if_previous_failed: true  # Игнорируй selection failure
    parallel: true

  - name: aggregation
    specialist: jury
    skip_if_previous_failed: false  # Требует всех трёх поэтов
```

---

## 6. Обработка ошибок в logic scripts

### Python logic script template

```python
#!/usr/bin/env python3
import json
import sys

def main(data_file):
    # Прочитай входные данные
    with open(data_file) as f:
        envelope = json.load(f)

    result_str = envelope.get('result', '')
    try:
        data = json.loads(result_str)
    except:
        # Fallback если результат не JSON
        data = {'text': result_str}

    # Выполни логику
    try:
        # Твой код здесь
        processed = transform(data)

        # Запиши результат обратно в файл
        with open(data_file, 'w') as f:
            json.dump({
                'stage': envelope.get('stage'),
                'result': json.dumps(processed),
                'timestamp': envelope.get('timestamp')
            }, f, indent=2)

        # Выход с кодом 0 = успех
        sys.exit(0)

    except Exception as e:
        print(f"Logic error: {e}", file=sys.stderr)
        # Выход с кодом 1 = ошибка
        sys.exit(1)

def transform(data):
    # Твоя логика
    return data

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <data_file>")
        sys.exit(1)
    main(sys.argv[1])
```

### Shell logic script template

```bash
#!/bin/bash
set -e

DATA_FILE="$1"
if [ -z "$DATA_FILE" ]; then
    echo "Usage: $0 <data_file>"
    exit 1
fi

# Твоя логика
# Если fail - выход с кодом 1
# Если success - выход с кодом 0

# Пример: проверка JSON
jq . "$DATA_FILE" > /dev/null || exit 1

echo "Logic completed successfully"
exit 0
```

---

## 7. Примеры полных процессов

### Пример 1: Pipeline с валидацией

```yaml
team: data-processing

blocks:
  - name: load_data
    specialist: data-loader
    continue_if_failed: false  # КРИТИЧНО
    # no skip_if_previous_failed (первый блок)

  - name: validate
    specialist: validator
    continue_if_failed: false  # КРИТИЧНО
    skip_if_previous_failed: false
    logic:
      validate: validate-schema.py

  - name: clean
    specialist: cleaner
    continue_if_failed: true   # ОПЦИОНАЛЬНО
    skip_if_previous_failed: false

  - name: transform
    specialist: transformer
    continue_if_failed: true   # ОПЦИОНАЛЬНО
    skip_if_previous_failed: false

  - name: backup
    specialist: backup
    continue_if_failed: true   # ОПЦИОНАЛЬНО
    skip_if_previous_failed: true  # Сделай резервную копию несмотря на ошибки

  - name: report
    specialist: reporter
    continue_if_failed: false  # КРИТИЧНО
    skip_if_previous_failed: false
```

### Пример 2: Параллельная обработка с отказоустойчивостью

```yaml
team: parallel-processing

blocks:
  - name: initialize
    specialist: init

  - name: process_batch_1
    specialist: processor
    depends_on: [initialize]
    parallel: true
    continue_if_failed: true  # Одна ошибка не блокирует другие батчи
    skip_if_previous_failed: false

  - name: process_batch_2
    specialist: processor
    depends_on: [initialize]
    parallel: true
    continue_if_failed: true
    skip_if_previous_failed: false

  - name: process_batch_3
    specialist: processor
    depends_on: [initialize]
    parallel: true
    continue_if_failed: true
    skip_if_previous_failed: false

  - name: aggregate_results
    specialist: aggregator
    depends_on: [process_batch_1, process_batch_2, process_batch_3]
    continue_if_failed: false  # Агрегация критична
    skip_if_previous_failed: false

  - name: cleanup
    specialist: cleanup
    depends_on: [aggregate_results]
    continue_if_failed: true  # Очистка не критична
    skip_if_previous_failed: true  # Очисти даже если было всё
```

### Пример 3: Творческий процесс с жюри

```yaml
team: creative

blocks:
  - name: ideation
    specialist: ideator
    continue_if_failed: false  # КРИТИЧНО - нет идей = нет процесса

  - name: creation_1
    specialist: creator
    depends_on: [ideation]
    parallel: true
    continue_if_failed: true  # Одна ошибка не блокирует других
    skip_if_previous_failed: false

  - name: creation_2
    specialist: creator
    depends_on: [ideation]
    parallel: true
    continue_if_failed: true
    skip_if_previous_failed: false

  - name: creation_3
    specialist: creator
    depends_on: [ideation]
    parallel: true
    continue_if_failed: true
    skip_if_previous_failed: false

  - name: jury_1
    specialist: jury
    depends_on: [creation_1, creation_2, creation_3]
    parallel: true
    continue_if_failed: true  # Один судья - не критично
    skip_if_previous_failed: false

  - name: jury_2
    specialist: jury
    depends_on: [creation_1, creation_2, creation_3]
    parallel: true
    continue_if_failed: true
    skip_if_previous_failed: false

  - name: final_judge
    specialist: final-judge
    depends_on: [jury_1, jury_2]
    continue_if_failed: false  # КРИТИЧНО - финал должен завершиться
    skip_if_previous_failed: false
```

---

## 8. Отладка и диагностика

### Просмотр логов

```bash
# Полные логи процесса
tail -f /tmp/dog-runs/run-20260101-120000/dog.log

# Логи конкретного блока (из logdir)
cat /tmp/dog-runs/run-20260101-120000/logs/my_block.log
```

### Проверка статуса

```bash
# Используя сокет команды
echo "status" | nc -U /tmp/dog-20260101-120000.sock

# Или через log entries
grep "WORKFLOW STOPPED" /tmp/dog-runs/run-20260101-120000/dog.log
```

### Типичные ошибки

| Ошибка | Причина | Решение |
|---|---|---|
| Block skipped | `skip_if_previous_failed=false` + была ошибка ранее | Установи `skip_if_previous_failed: true` если нужен |
| Workflow stopped | `continue_if_failed=false` на блоке, который упал | Проверь логику блока или смени на `continue_if_failed: true` |
| Dependency not met | Блок завис | Проверь `depends_on` и статусы dependency блоков |
| Validation failed | Logic script validation упала | Проверь JSON schema в validate script |

---

## 9. Лучшие практики

### DO (Делай)

✓ Явно указывай `continue_if_failed` и `skip_if_previous_failed` на критичных блоках
✓ Используй параллельный запуск для независимых операций
✓ Тестируй параметры в sandbox прежде чем запускать в продакшене
✓ Документируй причины выбора каждого параметра
✓ Используй логирование для отладки

### DON'T (Не делай)

✗ Полагайся на default параметры на критичных блоках
✗ Смешивай валидацию содержимого (subjective) с проверкой структуры
✗ Создавай очень длинные цепочки зависимостей (сложно отладить)
✗ Используй `continue_if_failed: false` без тщательного анализа
✗ Игнорируй ошибки в logic scripts - всегда проверяй exit code

---

## 10. Тестирование процессов

### Локальный тест процесса

```bash
# Создай test task
mkdir -p /tmp/test-task
cat > /tmp/test-task/task.yaml << 'EOF'
id: test-001
flow: my-flow
output_dir: ./outputs
EOF

# Запусти с паузой в начале
python3 dog.py --task /tmp/test-task --pause

# Посмотри первый блок
echo "list" | nc -U /tmp/dog-20260101-120000.sock

# Перейди к интересующему блоку и проверь логи
tail /tmp/dog-runs/run-20260101-120000/dog.log
```

### Проверка параметров

```bash
# Grep в YAML файле
grep -E "(continue_if_failed|skip_if_previous_failed)" agents/flows/my-flow/my-flow.yaml

# Должно быть явно указано на критичных блоках
# Пример правильного:
# - name: critical_block
#   continue_if_failed: false
#   skip_if_previous_failed: false
```

---

## Версия документа

- **Версия:** 2.5.3
- **Обновлено:** 2026-01-01
- **Применимо к:** Dog v2.5.3+

Для более новых версий смотри CHANGELOG.md.
