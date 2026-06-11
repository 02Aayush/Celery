# 🌿 Celery + Redis + Django — Learning Bootcamp

A self-paced bootcamp to learn Celery and Redis with Django, built on Windows 11 with WSL2.  
This repo documents the learning path, concepts, code, and how to test everything — so anyone can follow along.

---

## 📚 Learning Path

| Phase | Topic | Status |
|-------|-------|--------|
| Phase 1 | Celery Core — tasks, retries, states, chaining, groups | ✅ Done |
| Phase 2 | Celery Beat — scheduled & periodic tasks | 🔲 In Progress |
| Phase 3 | Redis Deep Dive — caching, data structures, TTL | 🔲 Planned |
| Phase 4 | Real World Patterns — progress bars, routing, Flower | 🔲 Planned |

---

## 🛠️ Setup

### Requirements

- Python 3.12
- Django 6.x
- Celery 5.6.x
- Redis (via WSL2 on Windows)

### Install

```bash
# clone the repo and create a virtual env
python -m venv env
env\Scripts\activate        # Windows
pip install django celery redis
```

### Project structure

```
myproject/
├── myproject/
│   ├── __init__.py         # loads celery app at startup
│   ├── celery.py           # celery app config
│   ├── settings.py
├── myapp/
│   ├── tasks.py            # all celery tasks
├── manage.py
```

### `myproject/__init__.py`

```python
from .celery import app as celery_app
__all__ = ['celery_app']
```

### `myproject/celery.py`

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

### `settings.py` (Celery config)

```python
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_TASK_TRACK_STARTED = True
```

### Start Redis (WSL2)

```bash
# inside WSL terminal
redis-server --daemonize yes
redis-cli ping    # should return PONG
```

### Start Celery Worker

```bash
# Windows — use --pool=solo to avoid billiard PermissionError on Windows
celery -A myproject worker -l info --pool=solo
```

> **Why `--pool=solo`?** Windows doesn't support Unix-style process forking. The `solo` pool runs tasks in the same process, avoiding shared memory errors from billiard (Celery's multiprocessing layer). Use Linux/WSL for production.

---

## ⚙️ How It Works (Simple)

```
Your Django code              Redis (broker)                 Celery Worker
──────────────────            ──────────────────             ─────────────
add.delay(2, 3)    ────────►  [ queue: "do add(2,3)" ]  ──► runs add(2,3)
                                                             stores result in Redis
result.get()       ◄────────  [ result: 5 ]
```

Think of Redis as a **post box**:
- Django **drops a letter** (task) into the box
- Celery **picks it up** and does the work
- The result is **stored back** in Redis for you to retrieve

---

## ✅ Phase 1 — Celery Core

### Topic 1 — Basic Tasks

The simplest Celery task. `delay()` sends it to the queue, `apply_async()` lets you control when it runs.

```python
# myapp/tasks.py
from celery import shared_task

@shared_task
def add(x, y):
    return x + y
```

```python
# Django shell
from myapp.tasks import add

result = add.delay(2, 3)            # fire and forget
print(result.get())                 # 5

result2 = add.apply_async((2, 3), countdown=5)  # run after 5 seconds
```

| Method | What it does |
|--------|-------------|
| `add.delay(2, 3)` | Send task to queue immediately |
| `add.apply_async((2, 3), countdown=5)` | Send task, run after 5 seconds |
| `result.get()` | Block and wait for result |
| `result.id` | Unique task ID (UUID) |

---

### Topic 2 — Retries

Auto-retry a task when it fails, with configurable delay and max attempts.

```python
@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def risky_task(self, x):
    try:
        if x < 10:
            raise ValueError("x is too small!")
        return f"Success! x={x}"
    except ValueError as e:
        raise self.retry(exc=e)
```

```python
# Django shell
result = risky_task.delay(5)    # fails, retries 3 times (4 total attempts)
result = risky_task.delay(15)   # succeeds immediately
```

**Flow:**

```
risky_task(5)
  → Attempt 1: FAIL  → wait 5s
  → Attempt 2: FAIL  → wait 5s
  → Attempt 3: FAIL  → wait 5s
  → Attempt 4: FAIL  → FAILURE (max retries reached)
```

| Parameter | Meaning |
|-----------|---------|
| `bind=True` | Gives task access to `self` (needed for `self.retry()`) |
| `max_retries=3` | 3 retries after the first attempt = 4 total |
| `default_retry_delay=5` | Wait 5 seconds between retries |
| `self.request.retries` | Current retry count (starts at 0) |

**Exponential backoff** — wait longer each retry:

```python
raise self.retry(exc=e, countdown=5 ** self.request.retries)
# waits: 1s → 5s → 25s → 125s
```

---

### Topic 3 — Task States

Track what a task is doing in real time using custom states and `AsyncResult`.

```python
@shared_task(bind=True)
def long_task(self, n):
    import time
    total = 0
    for i in range(n):
        time.sleep(1)
        total += i
        self.update_state(
            state='PROGRESS',
            meta={
                'current': i + 1,
                'total': n,
                'percent': round(((i + 1) / n) * 100)
            }
        )
    return {'status': 'done', 'result': total}
```

```python
# Django shell
from celery.result import AsyncResult

result = long_task.delay(5)

# poll every second
for _ in range(8):
    time.sleep(1)
    r = AsyncResult(result.id)
    print(r.state, r.info)
```

**State lifecycle:**

```
PENDING → STARTED → PROGRESS → PROGRESS → ... → SUCCESS
                                                 or FAILURE
                                                 or RETRY
```

| State | When |
|-------|------|
| `PENDING` | Task sent, not yet picked up |
| `STARTED` | Worker started it (requires `CELERY_TASK_TRACK_STARTED = True`) |
| `PROGRESS` | Custom state — you define this with `update_state()` |
| `SUCCESS` | Finished successfully |
| `FAILURE` | Raised an unhandled exception |
| `RETRY` | Waiting to retry |

> `AsyncResult(task_id)` — you only need the task ID to check status from anywhere. Redis stores the state.

---

### Topic 4 — Chaining

Run tasks in sequence where the output of one becomes the input of the next.

```python
@shared_task
def double(x):
    return x * 2

@shared_task
def square(x):
    return x ** 2

@shared_task
def make_negative(x):
    return -x
```

```python
# Django shell
from celery import chain
from myapp.tasks import double, square, make_negative

result = (double.s(3) | square.s() | make_negative.s()).delay()
# 3 → double → 6 → square → 36 → make_negative → -36

print(result.get())   # -36
```

**Flow:**

```
double(3) → 6 → square(6) → 36 → make_negative(36) → -36
```

| Code | Meaning |
|------|---------|
| `task.s(3)` | Signature — "call task with arg 3" (not run yet) |
| `task.s()` | Signature — will receive output of previous task |
| `\|` operator | Connects tasks into a chain |
| `.delay()` on chain | Actually sends the whole chain to the queue |

> If any task in a chain fails, **the rest are skipped**.

---

### Topic 5 — Groups

Run multiple tasks in parallel and collect all results.

```python
@shared_task
def multiply(x, y):
    return x * y
```

```python
# Django shell
from celery import group
from myapp.tasks import double, square, multiply

result = group(
    double.s(5),
    square.s(4),
    multiply.s(3, 7)
).delay()

print(result.ready())      # True when ALL tasks are done
print(result.successful()) # True if ALL succeeded
print(result.get())        # [10, 16, 21]
```

**Flow:**

```
         ┌── double(5)     → 10 ─┐
.delay() ─┤── square(4)    → 16 ─├──► [10, 16, 21]
         └── multiply(3,7) → 21 ─┘
              (all run in parallel)
```

**Group + Chain combo:**

```python
# double first, then square and multiply in parallel
pipeline = chain(
    double.s(5),
    group(square.s(), multiply.s(3))
)
result = pipeline.delay()
print(result.get())   # [100, 30]
```

**Chain vs Group:**

| | Chain | Group |
|--|-------|-------|
| Runs | One after another | All at once |
| Output feeds next | ✅ Yes | ❌ No |
| Result | Single value | List of values |
| Use when | Steps depend on each other | Tasks are independent |

---

## 🧪 How to Test

Always have 3 things running:

```
Terminal 1 (WSL)      → redis-server --daemonize yes
Terminal 2 (Windows)  → celery -A myproject worker -l info --pool=solo
Terminal 3 (Windows)  → python manage.py shell
```

In the worker terminal, a successful task looks like:

```
[INFO] Task myapp.tasks.add[uuid...] received
[INFO] Task myapp.tasks.add[uuid...] succeeded in 0.01s: 5
```

---

## 🐛 Troubleshooting

| Problem | Fix |
|---------|-----|
| `PermissionError [WinError 5]` | Use `--pool=solo` flag |
| `result.get()` hangs | Celery worker isn't running |
| `ConnectionError` to Redis | Run `redis-server --daemonize yes` in WSL |
| Task not found in worker | Check `myapp` is in `INSTALLED_APPS` |
| `localhost` Redis fails | Use WSL IP from `hostname -I` in broker URL |

---

## 📦 Full `tasks.py` (Phase 1)

```python
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@shared_task
def add(x, y):
    return x + y

@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def risky_task(self, x):
    try:
        logger.info(f"Attempt #{self.request.retries + 1} with x={x}")
        if x < 10:
            raise ValueError("x is too small!")
        return f"Success! x={x}"
    except ValueError as e:
        logger.warning(f"Failed: {e}. Retrying...")
        raise self.retry(exc=e)

@shared_task(bind=True)
def long_task(self, n):
    import time
    total = 0
    for i in range(n):
        time.sleep(1)
        total += i
        self.update_state(
            state='PROGRESS',
            meta={'current': i + 1, 'total': n, 'percent': round(((i + 1) / n) * 100)}
        )
    return {'status': 'done', 'result': total}

@shared_task
def double(x):
    return x * 2

@shared_task
def square(x):
    return x ** 2

@shared_task
def make_negative(x):
    return -x

@shared_task
def multiply(x, y):
    return x * y
```

---

*Updated as each phase is completed. Phase 2 and beyond coming soon.*
