# notif.py
import os
import logging
from email.message import EmailMessage
import smtplib

from twilio.rest import Client

logger = logging.getLogger("notif")
logger.setLevel(logging.INFO)

EMAIL_ADDRESS = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASS")
ENABLE_TTS = os.getenv("ENABLE_TTS", "false").lower() == "true"

def send_email(to: str, subject: str, body: str) -> None:
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        logger.warning("Email credentials not set; skipping email to %s", to)
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to
        msg.set_content(body)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        logger.info("Email sent to %s", to)
    except Exception:
        logger.exception("Failed to send email to %s", to)




def make_phone_call(to_number: str, message: str) -> None:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone = os.getenv("TWILIO_PHONE")
    if not (account_sid and auth_token and twilio_phone):
        logger.warning("Twilio credentials missing; skipping call to %s", to_number)
        return
    try:
        client = Client(account_sid, auth_token)
        call = client.calls.create(
            twiml=f'<Response><Say>{message}</Say></Response>',
            to=to_number,
            from_=twilio_phone
        )
        logger.info("Call initiated to %s sid=%s", to_number, call.sid)
    except Exception:
        logger.exception("Twilio call failed for %s", to_number)
import logging

logger = logging.getLogger("notif")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
