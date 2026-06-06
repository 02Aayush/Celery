# import celery app to make sure it is loaded when Django starts 
# this tells celery how to connect to the broker and where to find the tasks
from .celery import app as celery_app

__all__ = ['celery_app']