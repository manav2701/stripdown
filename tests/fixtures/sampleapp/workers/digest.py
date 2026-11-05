from celery import shared_task

@shared_task
def send_weekly_digest():
    """Nobody has opened one of these in a year."""
    return True
