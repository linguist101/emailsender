import os, signal, sys, time, json
import psycopg2, psycopg2.extras
from datetime import datetime, timezone
from emailer import Emailer, render_template, jitter


DB_URL = os.getenv("DB_URL")
SERVICE_NAME = os.getenv("SERVICE_NAME", "sendbot-worker")
GLOBAL_DAILY_CAP = int(os.getenv("GLOBAL_DAILY_CAP", "300"))


_shutdown = False


def handle_sigterm(signum, frame):
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGTERM, handle_sigterm)


def conn():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def heartbeat():
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO heartbeats(service_name, ts) VALUES(%s, NOW()) "
            "ON CONFLICT (service_name) DO UPDATE SET ts=EXCLUDED.ts",
            (SERVICE_NAME,)
        )
        c.commit()


def sent_today_count(c):
    with c.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM events WHERE type='sent' AND ts::date=CURRENT_DATE"
        )
        return cur.fetchone()["n"]


def inbox_headroom(c, inbox_id):
    with c.cursor() as cur:
        cur.execute(
            "SELECT daily_cap, pace_seconds, disabled FROM inboxes WHERE id=%s",
            (inbox_id,)
        )
        row = cur.fetchone()
        if not row or row["disabled"]:
            return (0, 60, True)
        daily_cap = row["daily_cap"]
        pace = row["pace_seconds"]
        cur.execute(
            "SELECT COUNT(*) AS n FROM events WHERE type='sent' "
            "AND inbox_id=%s AND ts::date=CURRENT_DATE",
            (inbox_id,)
        )
        sent = cur.fetchone()["n"]
        return (max(0, daily_cap - sent), pace, False)


def pick_inbox(c):
    with c.cursor() as cur:
        cur.execute(
            "SELECT id, smtp_host, smtp_port, username, password, from_name, from_email, health_score "
            "FROM inboxes WHERE NOT disabled ORDER BY health_score DESC, id ASC"
        )
        rows = cur.fetchall()
    for r in rows:
        head, pace, disabled = inbox_headroom(c, r["id"])
        if head > 0:
            loop()   # ⚠️ This line looks suspicious – do you really want to call loop() here?
