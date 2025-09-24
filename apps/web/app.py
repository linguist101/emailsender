import os
import csv
import io
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg import sql as psql  # <-- for safe script splitting

from fastapi import FastAPI, Request, Form, UploadFile, File, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown2 import Markdown

DB_URL = os.getenv("DB_URL") or os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("Missing DB_URL/DATABASE_URL env var.")

app = FastAPI()

# ----- run migration once on startup -----
def init_db():
    # apps/web/app.py -> repo root -> db/migrations/001_init.sql
    sql_path = Path(__file__).resolve().parents[2] / "db" / "migrations" / "001_init.sql"
    script = sql_path.read_text(encoding="utf-8")

    # Simple split on semicolon; safe for this migration (no functions/procedures)
    statements = [s.strip() for s in script.split(";") if s.strip()]

    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt + ";")
        conn.commit()

    print(f"[init_db] Applied migration from {sql_path}")

# Run on startup
init_db()



# Templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"])
)
md = Markdown(extras=["tables", "fenced-code-blocks"])

# Static directory (if you want CSS/JS later)
app.mount("/static", StaticFiles(directory=TEMPLATES_DIR), name="static")


# --- DB helper
def get_conn():
    return psycopg.connect(DB_URL, row_factory=dict_row)


# --- Render helper
def render(tpl, **ctx):
    template = env.get_template(tpl)
    return HTMLResponse(template.render(**ctx))


@app.get("/healthz")
def healthz():
    return {"ok": True, "time": datetime.utcnow().isoformat()}


# ---------- DASHBOARD ----------
@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
def dashboard():
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM events WHERE type='sent' AND ts::date=CURRENT_DATE"
        )
        sent_today = cur.fetchone()["n"]

        cur.execute(
            "SELECT COUNT(*) AS n FROM events WHERE type='bounce' AND ts::date=CURRENT_DATE"
        )
        bounces_today = cur.fetchone()["n"]

        cur.execute(
            "SELECT COUNT(*) AS n FROM events WHERE type='complaint' AND ts::date=CURRENT_DATE"
        )
        comp_today = cur.fetchone()["n"]

        cur.execute(
            "SELECT COUNT(*) AS n FROM unsubscribes WHERE ts::date=CURRENT_DATE"
        )
        unsubs_today = cur.fetchone()["n"]

        cur.execute("SELECT service_name, ts FROM heartbeats")
        heartbeats = cur.fetchall()

    return render(
        "dashboard.html",
        kpis={
            "sent_today": sent_today,
            "bounces_today": bounces_today,
            "complaints_today": comp_today,
            "unsubs_today": unsubs_today,
        },
        heartbeats=heartbeats,
    )


@app.get("/dashboard/inboxes")
def page_inboxes():
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT id,name,from_email,smtp_host,daily_cap,pace_seconds,health_score,disabled FROM inboxes ORDER BY id"
        )
        rows = cur.fetchall()
    return render("inboxes.html", rows=rows)


@app.post("/dashboard/inboxes/update")
async def update_inbox(
    inbox_id: int = Form(...),
    daily_cap: int = Form(...),
    pace_seconds: int = Form(...),
    disabled: str = Form("false"),
):
    flag = disabled.lower() == "true"
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE inboxes SET daily_cap=%s, pace_seconds=%s, disabled=%s WHERE id=%s",
            (daily_cap, pace_seconds, flag, inbox_id),
        )
        c.commit()
    return RedirectResponse(url="/dashboard/inboxes", status_code=303)


from fastapi import HTTPException

@app.get("/dashboard/inboxes/new")
def new_inbox_form():
    return render("inboxes_new.html")

@app.post("/dashboard/inboxes/create")
async def create_inbox(
    name: str = Form(...),
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
    username: str = Form(...),
    password: str = Form(...),
    from_name: str = Form(...),
    from_email: str = Form(...),
    daily_cap: int = Form(30),
    monthly_cap: int = Form(1000),
    pace_seconds: int = Form(90),
):
    if "@" not in from_email:
        raise HTTPException(status_code=400, detail="from_email must be a valid email")
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO inboxes
              (name, smtp_host, smtp_port, username, password, from_name, from_email,
               daily_cap, monthly_cap, pace_seconds, health_score, disabled)
            VALUES
              (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1.0,false)
            """,
            (name, smtp_host, smtp_port, username, password, from_name, from_email,
             daily_cap, monthly_cap, pace_seconds),
        )
        c.commit()
    return RedirectResponse(url="/dashboard/inboxes", status_code=303)



@app.get("/dashboard/campaigns")
def page_campaigns():
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.name, c.status, t.name AS template_name, c.daily_send_cap
            FROM campaigns c JOIN templates t ON t.id=c.template_id ORDER BY c.id DESC
            """
        )
        rows = cur.fetchall()
    return render("campaigns.html", rows=rows)


@app.post("/dashboard/campaigns/status")
async def set_campaign_status(campaign_id: int = Form(...), status_name: str = Form(...)):
    if status_name not in ("draft", "running", "paused", "done"):
        return Response("Invalid status", status_code=400)
    with get_conn() as c, c.cursor() as cur:
        cur.execute("UPDATE campaigns SET status=%s WHERE id=%s", (status_name, campaign_id))
        c.commit()
    return RedirectResponse(url="/dashboard/campaigns", status_code=303)


@app.get("/dashboard/queue")
def page_queue():
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT id,campaign_id,contact_id,subject,status,scheduled_at FROM send_queue ORDER BY id DESC LIMIT 200"
        )
        rows = cur.fetchall()
    return render("queue.html", rows=rows)


@app.get("/dashboard/events")
def page_events():
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT id,campaign_id,contact_id,inbox_id,type,ts,LEFT(COALESCE(meta::text,''),120) AS meta FROM events ORDER BY id DESC LIMIT 200"
        )
        rows = cur.fetchall()
    return render("events.html", rows=rows)


@app.get("/dashboard/contacts")
def page_contacts():
    return render("contacts.html")


@app.post("/dashboard/contacts/upload")
async def contacts_upload(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    required = {"email"}
    if not required.issubset(set([h.strip() for h in reader.fieldnames])):
        return Response("CSV must include at least 'email' column", status_code=400)
    rows = [r for r in reader]
    with get_conn() as c, c.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO contacts(email, first_name, last_name, company, tags, source, lawful_basis, consent_ts)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (email) DO UPDATE SET
                  first_name=EXCLUDED.first_name,
                  last_name=EXCLUDED.last_name,
                  company=EXCLUDED.company,
                  tags=EXCLUDED.tags,
                  source=EXCLUDED.source,
                  lawful_basis=EXCLUDED.lawful_basis,
                  consent_ts=EXCLUDED.consent_ts
                """,
                (
                    r.get("email"),
                    r.get("first_name"),
                    r.get("last_name"),
                    r.get("company"),
                    r.get("tags"),
                    r.get("source"),
                    r.get("lawful_basis"),
                    r.get("consent_ts"),
                ),
            )
        c.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


# ---------- Templates ----------
@app.get("/dashboard/templates")
async def templates_list():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id,name,subject FROM templates ORDER BY id DESC")
        rows = cur.fetchall()
    return render("templates_list.html", rows=rows)


@app.get("/dashboard/templates/edit")
async def templates_edit(id: int | None = None):
    tpl = None
    if id:
        with get_conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id,name,subject,body_markdown FROM templates WHERE id=%s", (id,)
            )
            tpl = cur.fetchone()
    return render("templates_edit.html", tpl=tpl)


@app.post("/dashboard/templates/save")
async def templates_save(
    name: str = Form(...),
    subject: str = Form(...),
    body_markdown: str = Form(...),
    id: int | None = Form(None),
):
    with get_conn() as c, c.cursor() as cur:
        if id:
            cur.execute(
                "UPDATE templates SET name=%s, subject=%s, body_markdown=%s WHERE id=%s",
                (name, subject, body_markdown, id),
            )
        else:
            cur.execute(
                "INSERT INTO templates(name,subject,body_markdown) VALUES(%s,%s,%s)",
                (name, subject, body_markdown),
            )
        c.commit()
    return RedirectResponse(url="/dashboard/templates", status_code=303)


# ---------- UNSUBSCRIBE ----------
@app.get("/u")
async def unsubscribe_get(e: str):
    masked = e[:2] + "***@" + e.split("@")[-1] if "@" in e else e
    return render("unsubscribe.html", email=masked)


@app.post("/u")
async def unsubscribe_post(e: str = Form(...), campaign_id: int | None = Form(None)):
    with get_conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO unsubscribes(email, ts, campaign_id) VALUES(%s, NOW(), %s) "
            "ON CONFLICT (email) DO UPDATE SET ts=EXCLUDED.ts, campaign_id=EXCLUDED.campaign_id",
            (e, campaign_id),
        )
        cur.execute(
            "INSERT INTO suppression(email, reason, ts) VALUES(%s, 'unsubscribe', NOW()) "
            "ON CONFLICT (email) DO UPDATE SET reason='unsubscribe', ts=EXCLUDED.ts",
            (e,),
        )
        cur.execute(
            "INSERT INTO events(campaign_id, contact_id, inbox_id, type, meta, ts) "
            "VALUES(%s, NULL, NULL, 'unsubscribe', to_jsonb(%s::text), NOW())",
            (campaign_id, e),
        )
        cur.execute(
            "UPDATE send_queue SET status='skipped' "
            "WHERE status='queued' AND contact_id IN (SELECT id FROM contacts WHERE email=%s)",
            (e,),
        )
        c.commit()
    return JSONResponse({"ok": True})


# ---------- API for Reply Bot ----------
@app.post("/api/reply")
async def api_reply(request: Request):
    if request.headers.get("X-Webhook-Secret") != WEBHOOK_SECRET:
        return Response(status_code=401)

    payload = await request.json()
    email = payload.get("email")
    campaign_id = payload.get("campaign_id")
    status_note = payload.get("status")
    snippet = payload.get("snippet")

    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id FROM contacts WHERE email=%s", (email,))
        row = cur.fetchone()
        contact_id = row["id"] if row else None
        cur.execute(
            "INSERT INTO events(campaign_id, contact_id, inbox_id, type, meta, ts) "
            "VALUES(%s, %s, NULL, 'reply', to_jsonb(%s::text), NOW())",
            (campaign_id, contact_id, snippet or status_note or "reply"),
        )
        cur.execute(
            "UPDATE send_queue SET status='skipped' WHERE status='queued' AND contact_id=%s",
            (contact_id,),
        )
        c.commit()
    return JSONResponse({"ok": True})


@app.get("/api/suppression")
async def api_suppression(email: str):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT 1 FROM suppression WHERE email=%s", (email,))
        sup = cur.fetchone() is not None
    return {"suppressed": sup}
