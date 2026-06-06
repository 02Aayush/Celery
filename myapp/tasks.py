from celery import shared_task

# task is a function that can be called asynchronously by celery workers
# the @shared_task decorator tells celery that this is a task that can be run asynchronously

# below is a simple task that adds two numbers together.
@shared_task
def add(x, y):
    return x + y