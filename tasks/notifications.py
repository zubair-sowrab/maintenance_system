import requests
from django.conf import settings

def send_telegram_msg(chat_id, text):
    token = "8906603431:AAGNy8bWHAxSMSYdZxY_GapVU8ee903S174"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    params = {'chat_id': chat_id, 'text': text}
    requests.post(url, data=params)