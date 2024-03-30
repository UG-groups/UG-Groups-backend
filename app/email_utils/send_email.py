from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import textwrap

from decouple import config
from jinja2 import Environment, FileSystemLoader


EMAIL_HOST = config('EMAIL_HOST', cast=str)
EMAIL_PORT = config('EMAIL_PORT', cast=str)
EMAIL_USERNAME = config('EMAIL_USERNAME', cast=str)
EMAIL_PASSWORD = config('EMAIL_PASSWORD', cast=str)
EMAIL_FROM = config('EMAIL_FROM', cast=str)


env = Environment(loader=FileSystemLoader("./app/email_utils/templates"))
template = env.get_template("verification_code.html")


def send_email(user_email, verification_code):
    message = MIMEMultipart("alternative")
    message["Subject"] = "Código de verificación"
    message["From"] = EMAIL_FROM
    message["To"] = user_email

    # write the text/plain part
    text = f"""
        UG Groups
        Tu código de verificación es: {verification_code}
    """
    # write the HTML part
    html = template.render({"verification_code": verification_code})

    # convert both parts to MIMEText objects and add them to the MIMEMultipart message
    plain_text_part = MIMEText(textwrap.dedent(text).strip(), "plain")
    html_part = MIMEText(html, "html")
    message.attach(plain_text_part)
    message.attach(html_part)

    # send your email
    with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT) as server:
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(
            EMAIL_FROM, user_email, message.as_string()
        )
