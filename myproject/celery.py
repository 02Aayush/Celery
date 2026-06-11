
import os
from celery import Celery
from celery.schedules import crontab
from myapp.tasks import heartbeat, cleanup_job

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')

# using a string ('django.conf:settings') here means the worker dosent't
# have to serialize the configuration object to
# child processes - namespace='CELERY' means all
# celery-related configuration keys should
# have a 'CELERY_' prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all the registered Django app configs.
app.autodiscover_tasks()

#  Register schedules 
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Every 5 seconds
    sender.add_periodic_task(5.0, heartbeat.s(), name='heartbeat every 5s')

    # Every 30 seconds
    sender.add_periodic_task(30.0, cleanup_job.s(), name='cleanup every 30s')

    # Crontab: every minute (like a cron job)
    sender.add_periodic_task(
        crontab(minute='*'),
        heartbeat.s(),
        name='heartbeat every minute (crontab)'
    )