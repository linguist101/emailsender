
import os
import time
import csv
import uuid
import sqlite3
from datetime import datetime
from email.message import EmailMessage

from dotenv import load_dotenv
from jinja2 import Template

import pandas as pd
import smtplib

DB_PATH = "sent_log.db"

def render_template(template_path, context):
    with open(template_path, "r", encoding="utf-8") as f:
        raw = f.read()
    # Split "Subject: ..." header from body
    if raw.startswith("Subject:"):
        subject_line, body = raw.split("\n", 1)
        subject = Template(subject_line.replace("Subject:", "").strip()).render(**context)
        body = Template(body).render(**context)
    else:
        subject = Template("{{subject}}").render(**context)
        body = Template(raw).render(**context)
    return subject.strip(), body.strip()

def make_message(subject, body, sender_name, sender_email, recipient, reply_to, unsubscribe_url):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient
    if reply_to:
        msg["Reply-To"] = reply_to
    # List-Unsubscribe headers for compliance and better deliverability
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body)
    return msg

def ensure_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sends (
        id TEXT PRIMARY KEY,
        email TEXT,
        template TEXT,
        subject TEXT,
        sent_at TEXT,
        status TEXT,
        message_id TEXT
    )
    """)
    con.commit()
    con.close()

def already_sent(email, template_name):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT 1 FROM sends WHERE email=? AND template=? LIMIT 1", (email, template_name))
    row = cur.fetchone()
    con.close()
    return row is not None

def log_send(email, template_name, subject, status, message_id=None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT INTO sends (id, email, template, subject, sent_at, status, message_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), email, template_name, subject, datetime.utcnow().isoformat(), status, message_id))
    con.commit()
    con.close()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Cold email sender")
    parser.add_argument("--csv", default="prospects.csv", help="Path to prospects CSV")
    parser.add_argument("--template", default="templates/email1.txt", help="Path to Jinja2 template file")
    parser.add_argument("--dry-run", action="store_true", help="Render only; do not send")
    parser.add_argument("--limit", type=int, default=None, help="Max emails this run (overrides MAX_PER_RUN)")
    args = parser.parse_args()

    load_dotenv()

    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SENDER_NAME = os.getenv("SENDER_NAME", "Outreach")
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    REPLY_TO = os.getenv("REPLY_TO", SENDER_EMAIL)
    UNSUBSCRIBE_URL_TMPL = os.getenv("UNSUBSCRIBE_URL", "")
    COMPANY_POSTAL = os.getenv("COMPANY_POSTAL_ADDRESS", "")

    MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "50"))
    SECONDS_BETWEEN = int(os.getenv("SECONDS_BETWEEN_EMAILS", "5"))
    per_run_limit = args.limit if args.limit is not None else MAX_PER_RUN

    # Load prospects
    df = pd.read_csv(args.csv).fillna("")
    ensure_db()

    # Connect SMTP if not dry-run
    server = None
    if not args.dry_run:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)

    sent_count = 0
    for _, row in df.iterrows():
        if sent_count >= per_run_limit:
            break

        recipient = row["email"].strip()
        if not recipient:
            continue

        template_name = os.path.basename(args.template)

        if already_sent(recipient, template_name):
            print(f"Skip (already sent): {recipient}")
            continue

        # Context for Jinja
        ctx = {
            "first_name": row.get("first_name","").strip() or "there",
            "company": row.get("company","").strip(),
            "role": row.get("role","").strip(),
            "sender_name": SENDER_NAME,
            "sender_email": SENDER_EMAIL,
            "company_postal": COMPANY_POSTAL,
            "unsubscribe_url": Template(UNSUBSCRIBE_URL_TMPL).render(email=recipient),
        }

        subject, body = render_template(args.template, ctx)
        msg = make_message(subject, body, SENDER_NAME, SENDER_EMAIL, recipient, REPLY_TO, ctx["unsubscribe_url"])

        print("="*60)
        print("To: ", recipient)
        print("Subject: ", subject)
        print(body[:500] + ("..." if len(body) > 500 else ""))

        if args.dry_run:
            log_send(recipient, template_name, subject, status="DRY_RUN")
            continue

        try:
            # send and capture message-id if returned
            response = server.send_message(msg)
            # smtplib returns an empty dict on success; message-id can be read from headers
            message_id = msg.get("Message-ID")
            log_send(recipient, template_name, subject, status="SENT", message_id=message_id)
            print("✅ Sent")
            sent_count += 1
            time.sleep(SECONDS_BETWEEN)
        except Exception as e:
            log_send(recipient, template_name, subject, status=f"ERROR: {e}")
            print("❌ Error:", e)

    if server is not None:
        server.quit()

if __name__ == "__main__":
    main()
