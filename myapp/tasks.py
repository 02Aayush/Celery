from celery import shared_task
from celery.utils.log import get_task_logger
# task is a function that can be called asynchronously by celery workers
# the @shared_task decorator tells celery that this is a task that can be run asynchronously

logger = get_task_logger(__name__)

# Basic Task
# below is a simple task that adds two numbers together.
@shared_task
def add(x, y):
    return x + y

# Task 1: Task Retries
# below is a more complex task that simulates a risky operation that may fail and needs to be retried
@shared_task(bind=True, max_tries=3, default_retry_delay=5)
def risky_task(self, x):
    try:
        logger.info(f"Attempt #{self.request.retries + 1} with x={x}")
        if x < 10:
            raise ValueError("x is too small!") # simulating a failure
        return f"Success! x={x}"
    except ValueError as e:
        logger.warning(f"failed: {e}. Rretrying...")
        raise self.retry(exc=e)

# Task 2: Task States / Task Progress Tracking
# below is a task that simulates a long-running operation and manually updates its state to track
@shared_task(bind=True)
def long_task(self, n):
    import time
    total = 0
    for i in range(n):
        time.sleep(1) # simulating a long-running task
        total += i
        # below we manually update the task state to 'PROGRESS' and 
        #include some custom metadata about the progress of the task.
        # This allows us to track the progress of the task from the client side if needed.
        # manually update the task state with custom info
        self.update_state(
            state='PROGRESS',
            meta={
                'current': i + 1,
                'total': n,
                'percent': round(((i + 1) / n) * 100)
            }
        )
    return {'status': 'done', 'result': total}

# Task 3: Chaining Tasks
# below are some simple tasks that can be chained together to create a workflow.
@shared_task
def double(x):
    logger.info(f"Doubling {x}")
    return x * 2

@shared_task
def square(x):
    logger.info(f"Squaring {x}")
    return x * x

@shared_task
def make_negative(x):
    logger.info(f"Making {x} negative")
    return -x

@shared_task
def add(x):
    logger.info(f"Adding {x} to itself")
    return x + x

# Task 4: Groups (Parallel Tasks)
# Group inside a chain — run tasks in parallel, then process all results together
@shared_task
def multiply(x, y):
    logger.info(f"Multiplying {x} * {y}")
    return x * y

'''
                    Chain                       Group
Runs:               One after another           All at once
Output feeds next:  Yes                         No
Use case:           Sequential workflows        Parallelizable tasks
Results:            Single value                List of results
Use when:           Steps depend on each other  Tasks are independent 
'''