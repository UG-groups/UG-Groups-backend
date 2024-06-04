import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from decouple import config
from jinja2 import Environment, FileSystemLoader
from pydantic import EmailStr


ORIGIN = config("ORIGIN", cast=str)

EMAIL_HOST = config('EMAIL_HOST', cast=str)
EMAIL_PORT = config('EMAIL_PORT', cast=str)
EMAIL_USERNAME = config('EMAIL_USERNAME', cast=str)
EMAIL_PASSWORD = config('EMAIL_PASSWORD', cast=str)
EMAIL_FROM = config('EMAIL_FROM', cast=str)


env = Environment(loader=FileSystemLoader("./app/email_utils/templates"))


def send_email(destination_email: EmailStr, subject: str, html_content):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = EMAIL_FROM
    message["To"] = destination_email

    # converts html content to a MIMEText object and add it to the MIMEMultipart message
    message.attach(MIMEText(html_content, "html"))

    # send your email
    with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT) as server:
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(
            EMAIL_FROM, destination_email, message.as_string()
        )


def send_verification_code_email(destination_email, verification_code):
    template = env.get_template("verification_code.html")
    html_content = template.render({"verification_code": verification_code})

    send_email(
        destination_email,
        "Código de verificación",
        html_content
    )


def send_password_reset_email(destination_email, token):
    template = env.get_template("password_reset.html")
    html_content = template.render({"origin": ORIGIN, "token": token})

    send_email(
        destination_email,
        "Solicitud de restauración de contraseña",
        html_content
    )
