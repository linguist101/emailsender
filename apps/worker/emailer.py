import os, smtplib, email.utils, time, random
from email.mime.text import MIMEText
from jinja2 import Template


APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
UNSUBSCRIBE_INBOX = os.getenv("UNSUBSCRIBE_INBOX", "unsubscribe@yourdomain.com")


class Emailer:
def __init__(self, host, port, user, pwd, from_name, from_email):
self.host = host
self.port = int(port)
self.user = user
self.pwd = pwd
self.from_name = from_name
self.from_email = from_email


def _build(self, to_email, subject, html_body):
msg = MIMEText(html_body, "html", "utf-8")
msg['Subject'] = subject
msg['From'] = email.utils.formataddr((self.from_name, self.from_email))
msg['To'] = to_email
list_unsub_url = f"{APP_BASE_URL}/u?e={to_email}"
list_unsub_mailto = f"mailto:{UNSUBSCRIBE_INBOX}?subject=unsubscribe&body={to_email}"
msg['List-Unsubscribe'] = f"<{list_unsub_mailto}>, <{list_unsub_url}>"
msg['List-Unsubscribe-Post'] = "List-Unsubscribe=One-Click"
msg['Date'] = email.utils.formatdate(localtime=True)
msg['Message-ID'] = email.utils.make_msgid()
return msg


def send(self, to_email, subject, html_body):
msg = self._build(to_email, subject, html_body)
with smtplib.SMTP(self.host, self.port, timeout=30) as s:
s.starttls()
s.login(self.user, self.pwd)
s.sendmail(self.from_email, [to_email], msg.as_string())




def render_template(subject_tpl: str, body_md: str, contact: dict) -> tuple[str, str]:
s = Template(subject_tpl).render(**contact)
# very simple: convert markdown line breaks to <br>
body = Template(body_md).render(**contact)
html = body.replace('\n', '<br>')
return s, html




def jitter(seconds: int, pct: float = 0.2) -> float:
if seconds <= 0:
return 0
span = seconds * pct
return max(0, seconds + random.uniform(-span, span))
