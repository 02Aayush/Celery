# 🌿 Celery + Redis + Django — Learning Bootcamp

A self-paced bootcamp to learn Celery and Redis with Django, built on Windows 11 with WSL2.  
This repo documents the learning path, concepts, code, and how to test everything — so anyone can follow along.

---

## 📚 Learning Path

| Phase | Topic | Status |
|-------|-------|--------|
| Phase 1 | Celery Core — tasks, retries, states, chaining, groups | ✅ Done |
| Phase 2 | Celery Beat — scheduled & periodic tasks | ✅ Done |
| Phase 3 | Redis Deep Dive — caching, data structures, TTL | 🔲 In Progress |
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

---

## ✅ Phase 2 — Celery Beat

### Topic 1 — How Beat Works

Beat is a separate scheduler process that drops tasks into the Redis queue on a timer. The worker picks them up exactly like any other task — it has no idea they came from Beat.

```
Celery Beat                   Redis (broker)                 Celery Worker
───────────                   ──────────────                 ─────────────
every 5s: heartbeat() ──────► [ queue: "do heartbeat()" ] ──► runs heartbeat()
every 1m: cleanup_job() ────► [ queue: "do cleanup_job()" ] ─► runs cleanup_job()
```

**Two processes, always running together:**

```
Terminal 1 (WSL)      → redis-server --daemonize yes
Terminal 2 (Windows)  → celery -A myproject worker -l info --pool=solo
Terminal 3 (Windows)  → celery -A myproject beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

> Beat must be restarted if you add schedules in code (`celery.py`). Schedules added via Django admin are picked up live — no restart needed.

---

### Topic 2 — Install & Setup (django-celery-beat)

`django-celery-beat` stores schedules in the Django database so they survive restarts and can be managed from the admin.

```bash
pip install django-celery-beat
python manage.py migrate    # creates Beat's schedule tables
python manage.py createsuperuser  # needed to access admin
```

```python
# settings.py — add to INSTALLED_APPS and point Beat at the DB scheduler
INSTALLED_APPS = [
    # ... existing apps ...
    'django_celery_beat',
]

CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```

| Table created by migration | Purpose |
|---------------------------|---------|
| `django_celery_beat_intervalschedule` | Every N seconds/minutes/hours |
| `django_celery_beat_crontabschedule` | Cron-style schedules |
| `django_celery_beat_clockedschedule` | Run once at a specific datetime |
| `django_celery_beat_periodictask` | Links a task to any schedule above |

---

### Topic 3 — Interval Schedules (code-defined)

Define periodic tasks directly in `celery.py` using `add_periodic_task()`. Fires every N seconds.

```python
# myapp/tasks.py — add these two tasks
@shared_task
def heartbeat():
    logger.info("💓 Heartbeat task fired!")
    return "alive"

@shared_task
def cleanup_job():
    logger.info("🧹 Cleanup job ran")
    return "cleaned"
```

```python
# myproject/celery.py — register schedules at app startup
import os
from celery import Celery
from celery.schedules import crontab
from myapp.tasks import heartbeat, cleanup_job

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(5.0,  heartbeat.s(),   name='heartbeat every 5s')
    sender.add_periodic_task(30.0, cleanup_job.s(), name='cleanup every 30s')
```

```
# Worker terminal — what you should see every 5 seconds
[INFO] Task myapp.tasks.heartbeat[uuid...] received
[INFO] 💓 Heartbeat task fired!
[INFO] Task myapp.tasks.heartbeat[uuid...] succeeded in 0.001s: 'alive'
```

| Parameter | Meaning |
|-----------|---------|
| `5.0` | Fire every 5 seconds |
| `heartbeat.s()` | Signature with no args — Beat calls this on schedule |
| `name=` | Human-readable label shown in Beat logs and admin |
| `on_after_finalize.connect` | Hook that runs after all apps are loaded — safe place to register schedules |

---

### Topic 4 — Crontab Schedules (code-defined)

Use `crontab()` for precise timing — same syntax as Unix cron. Minute, hour, day of week, etc.

```python
# myproject/celery.py — add inside setup_periodic_tasks()
from celery.schedules import crontab

@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    # every 5 seconds (interval)
    sender.add_periodic_task(5.0, heartbeat.s(), name='heartbeat every 5s')

    # every minute (crontab)
    sender.add_periodic_task(
        crontab(minute='*'),
        heartbeat.s(),
        name='heartbeat every minute'
    )

    # every day at 9:00 AM
    sender.add_periodic_task(
        crontab(hour='9', minute='0'),
        cleanup_job.s(),
        name='daily cleanup at 9am'
    )
```

**Crontab quick reference:**

```
crontab(minute='*/5')              → every 5 minutes
crontab(hour='8', minute='0')      → every day at 8:00 AM
crontab(day_of_week='mon-fri')     → every weekday at midnight
crontab(minute='0', hour='*/2')    → every 2 hours
crontab(day_of_month='1')          → 1st of every month at midnight
crontab(minute='*')                → every minute
```

| Field | Values | Example |
|-------|--------|---------|
| `minute` | `0–59`, `*`, `*/N` | `'*/15'` = every 15 min |
| `hour` | `0–23`, `*`, `*/N` | `'9'` = 9 AM |
| `day_of_week` | `0–6`, `mon–sun` | `'mon-fri'` = weekdays |
| `day_of_month` | `1–31`, `*` | `'1'` = 1st of month |
| `month_of_year` | `1–12`, `*` | `'*'` = every month |

> `crontab()` with no args fires every minute — same as `* * * * *` in Unix cron.

---

### Topic 5 — Admin-Managed Schedules (django-celery-beat)

Create, pause, and delete schedules from the Django admin without touching code or restarting anything.

```
http://127.0.0.1:8000/admin/   →   Periodic Tasks section
```

**Creating an interval task from admin:**

```
1. Admin → Intervals → Add
   Every: 10   Period: seconds   → Save

2. Admin → Periodic Tasks → Add
   Name:      double every 10s
   Task:      myapp.tasks.double
   Interval:  (select the one you just made)
   Arguments: [7]              ← JSON array, becomes double(7)
   → Save
```

```
# Worker terminal — fires every 10 seconds
[INFO] Task myapp.tasks.double[uuid...] received
[INFO] Doubling 7
[INFO] Task myapp.tasks.double[uuid...] succeeded in 0.001s: 14
```

**Flow — how Beat picks up admin changes:**

```
Django Admin save
      │
      ▼
django_celery_beat_periodictask (DB row updated)
      │
      ▼  (Beat polls DB every few seconds)
Celery Beat detects change → "DatabaseScheduler: Schedule changed."
      │
      ▼
Task dropped into Redis queue on next interval
      │
      ▼
Worker executes it
```

| Admin action | Effect | Restart needed? |
|-------------|--------|----------------|
| Add new task | Beat picks it up on next poll | ❌ No |
| Uncheck **Enabled** | Task stops firing immediately | ❌ No |
| Re-enable | Resumes on next poll | ❌ No |
| Change interval | New schedule applied live | ❌ No |
| Delete task | Stops permanently | ❌ No |

> Disabling a runaway task from admin without a deployment is the main operational superpower of `django-celery-beat`.

---

### Topic 6 — Crontab Schedules from Admin

Same as interval but with crontab precision — set exact minute/hour/day combinations from the UI.

```
1. Admin → Crontabs → Add
   Minute:        */1
   Hour:          *
   Day of week:   *
   Day of month:  *
   Month of year: *
   → Save   (fires every minute)

2. Admin → Periodic Tasks → Add
   Name:      square every minute
   Task:      myapp.tasks.square
   Crontab:   (select the one you just made)
   Arguments: [4]              ← square(4)
   → Save
```

```
# Worker terminal — fires at the top of every minute
[INFO] Task myapp.tasks.square[uuid...] received
[INFO] Squaring 4
[INFO] Task myapp.tasks.square[uuid...] succeeded in 0.001s: 16
```

**Daily report pattern — real-world example:**

```
Crontab:  minute=0, hour=9, everything else *
Task:     myapp.tasks.cleanup_job
Name:     daily report at 9am
```

> The task name in admin must exactly match what `celery inspect registered` returns. A mismatch causes Beat to silently skip it.

---

### Topic 7 — One-off Clocked Tasks

Run a task exactly once at a specific future datetime — then never again.

```
1. Admin → Clocked → Add
   Clocked time: 2025-06-15 09:30:00   → Save

2. Admin → Periodic Tasks → Add
   Name:      one-time cleanup June 15
   Task:      myapp.tasks.cleanup_job
   Clocked:   (select the one you just made)
   ☑ One-off task              ← critical checkbox
   → Save
```

**Flow:**

```
Beat running...
  → 09:29:59  nothing
  → 09:30:00  drops cleanup_job() into queue  →  worker executes it
  → 09:30:05  task marked done, never fires again
```

| Field | Meaning |
|-------|---------|
| **Clocked time** | Exact UTC datetime to fire |
| **One-off task** ☑ | Task is disabled automatically after it fires once |

> Always use UTC for clocked times unless you've configured Django's `TIME_ZONE` and `USE_TZ` carefully.

---

## 📦 Full Beat config (Phase 2)

### `myproject/celery.py`

```python
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    from myapp.tasks import heartbeat, cleanup_job

    # Interval — every 5 seconds
    sender.add_periodic_task(5.0, heartbeat.s(), name='heartbeat every 5s')

    # Interval — every 30 seconds
    sender.add_periodic_task(30.0, cleanup_job.s(), name='cleanup every 30s')

    # Crontab — every minute
    sender.add_periodic_task(
        crontab(minute='*'),
        heartbeat.s(),
        name='heartbeat every minute'
    )

    # Crontab — every day at 9 AM
    sender.add_periodic_task(
        crontab(hour='9', minute='0'),
        cleanup_job.s(),
        name='daily cleanup at 9am'
    )
```

### `settings.py` additions (Phase 2)

```python
INSTALLED_APPS = [
    # ... existing ...
    'django_celery_beat',
]

CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```

### New tasks added to `myapp/tasks.py`

```python
@shared_task
def heartbeat():
    logger.info("💓 Heartbeat task fired!")
    return "alive"

@shared_task
def cleanup_job():
    logger.info("🧹 Cleanup job ran")
    return "cleaned"
```

### Start commands (Phase 2 — 3 terminals + admin)

```
Terminal 1 (WSL)      → redis-server --daemonize yes
Terminal 2 (Windows)  → celery -A myproject worker -l info --pool=solo
Terminal 3 (Windows)  → celery -A myproject beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
Browser               → http://127.0.0.1:8000/admin/  (manage schedules live)
```

---

---

## 🔲 Phase 3 — Redis Deep Dive

### Topic 1 — Redis Data Structures Celery Actually Uses

Celery uses Redis as a plain key-value + list store. `redis-cli` lets you see exactly what gets written when a task fires.

```bash
# redis-cli
KEYS *
```

```
1) "celery"                          ← the default task queue (a List)
2) "_kombu.binding.celery"           ← Kombu's queue registry
3) "celery-task-meta-<uuid>"         ← result of a completed task
```

```bash
# redis-cli — watch every command live as a task runs
MONITOR
```

```python
# Django shell — in a separate terminal, fire a task while MONITOR is running
from myapp.tasks import add
result = add.delay(2, 3)
```

```
# MONITOR output
"LPUSH" "celery" "<task message JSON>"   ← drops task into the queue list
"SET" "celery-task-meta-<uuid>" "..."    ← stores result after worker runs it
```

```bash
# Inspect the queue and a result directly
LLEN celery                                  # how many tasks waiting
LINDEX celery 0                              # peek at the first task (JSON)
GET celery-task-meta-<uuid>                  # task result + state
```

```json
{"status": "SUCCESS", "result": 30, "traceback": null, "task_id": "uuid", ...}
```

| Redis key pattern | Type | What it stores |
|---|---|---|
| `celery` | List | The default task queue — pending tasks |
| `_kombu.binding.celery` | Set | Kombu's internal queue binding registry |
| `celery-task-meta-<uuid>` | String | Task result, state, traceback |

> Redis Lists are used as queues: `LPUSH` adds to the left (enqueue), `BRPOP` removes from the right (dequeue). The worker does `BRPOP celery` in a blocking loop, waking instantly when a task arrives.

> If `GET celery-task-meta-<uuid>` returns `(nil)`, it usually means the worker never picked up the task (check `LLEN celery` and worker logs) — not that the result expired. Always confirm with `celery -A myproject inspect ping` that the worker is alive and connected.

---

### Topic 2 — Monitoring Queues & What to Do When They Pile Up

`LLEN` tells you what's waiting. `celery inspect` tells you what the worker is actually doing. Use both together to diagnose a backlog.

```bash
# redis-cli — the vital sign
LLEN celery
```

```
0    → healthy, nothing waiting
50   → worker is behind or down
5000 → something is seriously wrong
```

```bash
# Watch it over time
watch -n 2 redis-cli LLEN celery
```

```bash
# Worker's point of view
celery -A myproject inspect active      # tasks currently executing
celery -A myproject inspect reserved    # pulled by worker, not started yet
celery -A myproject inspect scheduled   # waiting on a future ETA/countdown
celery -A myproject inspect ping        # is the worker alive at all
```

```python
# Example: inspect active output
{
    'celery@DESKTOP-ABC123': [
        {'id': '569df05b-...', 'name': 'myapp.tasks.long_task', 'args': [30], 'time_start': 1234567.89}
    ]
}
```

**Flow — diagnosing a pile-up:**

```
Queue growing because:
  1. Worker crashed/not running     → restart it
  2. Worker pool too small          → only 1 task at a time with --pool=solo
  3. One task type is slow          → blocking everything behind it
  4. Tasks failing + retrying       → re-queuing endlessly
```

```bash
# Clearing a stuck/poisoned queue — DESTRUCTIVE, dev only
celery -A myproject purge              # asks for confirmation
redis-cli DEL celery                   # no confirmation, direct
celery -A myproject control revoke <task_id>   # cancel one specific task
```

| Command | Tells you / Does |
|---|---|
| `redis-cli LLEN celery` | How many tasks are queued, untouched |
| `inspect active` | What the worker is executing right now |
| `inspect reserved` | What worker grabbed but hasn't started (prefetch buffer) |
| `inspect scheduled` | Tasks waiting on a future ETA/countdown |
| `celery -A myproject purge` | Removes all pending tasks, asks confirmation |
| `control revoke <task_id>` | Cancels one task by ID, won't run even if picked up |

> With `--pool=solo` (required on Windows), the worker processes one task at a time, sequentially. A single `long_task(60)` blocks everything behind it for 60 seconds — normal in dev, but the reason Topic 3 (routing) exists.

> Never purge in production without checking `inspect active`/`reserved` first — you'll silently lose queued work.

---

### Topic 3 — Multiple Queues & Task Routing

Route specific tasks to specific named queues, then run dedicated workers per queue so slow tasks can't block fast ones.

```python
# settings.py
CELERY_TASK_ROUTES = {
    'myapp.tasks.long_task': {'queue': 'slow_jobs'},
    'myapp.tasks.heartbeat': {'queue': 'high_priority'},
    'myapp.tasks.cleanup_job': {'queue': 'high_priority'},
    # anything not listed here falls back to the default 'celery' queue
}
```

```bash
# Terminal A — handles only slow_jobs
celery -A myproject worker -l info --pool=solo -Q slow_jobs -n slow_worker@%h

# Terminal B — handles only high_priority
celery -A myproject worker -l info --pool=solo -Q high_priority -n fast_worker@%h

# Terminal C — handles the default queue
celery -A myproject worker -l info --pool=solo -Q celery -n default_worker@%h
```

```python
# Django shell
from myapp.tasks import long_task, heartbeat, add

long_task.delay(20)   # → slow_jobs queue → only slow_worker picks it up
heartbeat.delay()     # → high_priority queue → only fast_worker picks it up
add.delay(2, 3)       # → default 'celery' queue → only default_worker picks it up
```

```bash
# redis-cli — confirm separate queue lists exist
LLEN slow_jobs
LLEN high_priority
LLEN celery
```

```bash
# Alternative — one worker, multiple queues, drained left-to-right by priority
celery -A myproject worker -l info --pool=solo -Q high_priority,celery,slow_jobs
```

```python
# Pattern-based routing — CELERY_TASK_ROUTES doesn't support glob patterns,
# so use a router function for wildcard-style matching
def route_task(name, args, kwargs, options, task=None, **kw):
    if name.startswith('myapp.tasks.slow_'):
        return {'queue': 'slow_jobs'}
    return {'queue': 'celery'}

CELERY_TASK_ROUTES = (route_task,)
```

**Flow — before vs after routing:**

```
BEFORE (single queue):
celery queue: [long_task(60), add(2,3), add(5,5)]
worker: ─ long_task ─────────────────────(60s)─ add(2,3) ─ add(5,5)
                                                  ↑ blocked 60s!

AFTER (routed queues):
slow_jobs:     [long_task(60)]        → slow_worker:    ─ long_task ──(60s)─
high_priority: [add(2,3), add(5,5)]   → default_worker: ─ add(2,3) ─ add(5,5) ─
                                                            ↑ instant, unblocked
```

| Concept | Meaning |
|---|---|
| `CELERY_TASK_ROUTES` | Maps task name → queue name |
| `-Q queue_name` | Worker flag — only listen to this queue (comma-separate for multiple) |
| `-n worker_name@%h` | Names the worker (useful when running several at once) |
| Separate queue per task type | Slow tasks can't block fast tasks anymore |
| Router function | Use for pattern-based routing instead of exact task names |

> Always restart workers after changing `CELERY_TASK_ROUTES` — routing is read at worker startup, not live like admin-managed Beat schedules.

---

### Topic 4 — Queue Priorities 🔲 NEXT

🔲 Not yet covered — picking up here next session.

Planned: jumping specific tasks ahead of others *within* the same queue using `priority` in `apply_async()`, without needing separate queues.

---

### Topic 5 — `celery inspect` & Control 🔲 PLANNED

🔲 Not yet covered.

Planned: deeper live worker interrogation and control — active/reserved/scheduled in more detail, plus revoking and rate-limiting tasks from the command line.

---

*Updated as each phase is completed. Phase 3 in progress — Topics 1–3 done, Topic 4 (queue priorities) next.*