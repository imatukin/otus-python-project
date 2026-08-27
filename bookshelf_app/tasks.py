from celery import shared_task
from django.core.mail import send_mail
import time


@shared_task
def add(x, y):
    time.sleep(7)
    return x + y


@shared_task
def send_mail_task(rec_email, subject, message):
    """Фоновая отправка почты"""
    send_mail(
        subject=subject,
        message=message,
        recipient_list=[rec_email],
        from_email='admin@mail.ru'
    )
    return f"Email sent tp {rec_email}"
