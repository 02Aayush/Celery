# Celery

A simple Celery learning guide for Windows with Django and Redis.

## Prerequisites

- WSL installed
- Redis installed in WSL

Redis installation guide:
- https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-on-windows/

> Note: Start Redis every time you open WSL:
> `redis-server --daemonize yes`

## Recommended terminals

- WSL terminal: run Redis
- Windows terminal 1: run Django
- Windows terminal 2: run Celery worker

## Run Django and Celery

In Windows terminal 1:

```powershell
env\Scripts\activate
python manage.py runserver
```

In Windows terminal 2:

```powershell
celery -A myproject worker -l info --pool=solo
```

> For basic learning, `python manage.py shell` is enough and you may skip `runserver`.

## How Celery works

Your Django code → Redis (message broker) → Celery worker

```text
How Redis + Celery works (simple) - 

Your Django code          Redis (message broker)       Celery Worker
─────────────────         ──────────────────────       ─────────────
add.delay(2, 3)  ──────>  [task queue: "do add(2,3)"] ──────>  runs add(2,3)
                                                                stores result back in Redis
result.get()     <──────  [result: 5]
```

## Example usage

```python
env\Scripts\activate
python manage.py shell
```

```python
from myapp.tasks import add

result = add.delay(2, 3)
print(result.id)        # unique task ID, e.g. "bd5c8464-..."
print(result.status)    # 'PENDING' or 'SUCCESS'
print(result.get())     # waits and returns 5

result2 = add.apply_async((10, 20), countdown=5)  # runs after 5 seconds
print(result2.status)   # 'PENDING' right now
import time

time.sleep(6)
print(result2.status)   # 'SUCCESS' now
print(result2.get())    # 30
```

## Expected output

```text
[INFO/MainProcess] Task myapp.tasks.add[bd5c8464-...] received
[INFO/MainProcess] Task myapp.tasks.add[bd5c8464-...] succeeded in 0.01s: 5
```
