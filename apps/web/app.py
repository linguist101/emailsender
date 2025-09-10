import os
rows = cur.fetchall()
return render("templates_list.html", rows=rows)


@app.get("/dashboard/templates/edit")
async def templates_edit(id: int | None = None):
tpl = None
if id:
with get_conn() as c, c.cursor() as cur:
cur.execute("SELECT id,name,subject,body_markdown FROM templates WHERE id=%s", (id,))
tpl = cur.fetchone()
return render("templates_edit.html", tpl=tpl)


@app.post("/dashboard/templates/save")
async def templates_save(name: str = Form(...), subject: str = Form(...), body_markdown: str = Form(...), id: int | None = Form(None)):
with get_conn() as c, c.cursor() as cur:
if id:
cur.execute("UPDATE templates SET name=%s, subject=%s, body_markdown=%s WHERE id=%s", (name, subject, body_markdown, id))
else:
cur.execute("INSERT INTO templates(name,subject,body_markdown) VALUES(%s,%s,%s)", (name, subject, body_markdown))
c.commit()
return RedirectResponse(url="/dashboard/templates", status_code=303)


# ---------- UNSUBSCRIBE (GET confirm + POST one‑click) ----------
@app.get("/u")
async def unsubscribe_get(e: str):
masked = e[:2] + "***@" + e.split('@')[-1] if '@' in e else e
return render("unsubscribe.html", email=masked)


@app.post("/u")
async def unsubscribe_post(e: str = Form(...), campaign_id: int | None = Form(None)):
with get_conn() as c, c.cursor() as cur:
cur.execute("INSERT INTO unsubscribes(email, ts, campaign_id) VALUES(%s, NOW(), %s) ON CONFLICT (email) DO UPDATE SET ts=EXCLUDED.ts, campaign_id=EXCLUDED.campaign_id", (e, campaign_id))
cur.execute("INSERT INTO suppression(email, reason, ts) VALUES(%s, 'unsubscribe', NOW()) ON CONFLICT (email) DO UPDATE SET reason='unsubscribe', ts=EXCLUDED.ts", (e,))
cur.execute("INSERT INTO events(campaign_id, contact_id, inbox_id, type, meta, ts) VALUES(%s, NULL, NULL, 'unsubscribe', to_jsonb(%s::text), NOW())", (campaign_id, e))
cur.execute("UPDATE send_queue SET status='skipped' WHERE status='queued' AND contact_id IN (SELECT id FROM contacts WHERE email=%s)", (e,))
c.commit()
return JSONResponse({"ok": True})


# ---------- API for Reply Bot ----------
@app.post("/api/reply")
async def api_reply(request: Request):
if request.headers.get('X-Webhook-Secret') != WEBHOOK_SECRET:
return Response(status_code=401)
payload = await request.json()
email = payload.get('email')
campaign_id = payload.get('campaign_id')
status_note = payload.get('status')
snippet = payload.get('snippet')
with get_conn() as c, c.cursor() as cur:
cur.execute("SELECT id FROM contacts WHERE email=%s", (email,))
row = cur.fetchone()
contact_id = row['id'] if row else None
cur.execute("INSERT INTO events(campaign_id, contact_id, inbox_id, type, meta, ts) VALUES(%s, %s, NULL, 'reply', to_jsonb(%s::text), NOW())", (campaign_id, contact_id, snippet or status_note or 'reply'))
# Pause any queued sends for this contact
cur.execute("UPDATE send_queue SET status='skipped' WHERE status='queued' AND contact_id=%s", (contact_id,))
c.commit()
return JSONResponse({"ok": True})


@app.get("/api/suppression")
async def api_suppression(email: str):
with get_conn() as c, c.cursor() as cur:
cur.execute("SELECT 1 FROM suppression WHERE email=%s", (email,))
sup = cur.fetchone() is not None
return {"suppressed": sup}
