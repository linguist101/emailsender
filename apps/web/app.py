import os

rows = cur.fetchall()
return render("templates_list.html", rows=rows)


@app.get("/dashboard/templates/edit")
async def templates_edit(id: int | None = None):
    tpl = None
    if id:
        with get_conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id,name,subject,body_markdown FROM templates WHERE id=%s",
                (id,)
            )
            tpl = cur.fetchone()
    return render("templates_edit.html", tpl=tpl)


@app.post("/dashboard/templates/save")
async def templates_save(
    name: str = Form(...),
    subject: str = Form(...),
    body_markdown: str = Form(...),
    id: int | None = Form(None)
):
    with get_conn() as c, c.cursor() as cur:
        if id:
            cur.execute(
                "UPDATE templates SET name=%s, subject=%s, body_markdown=%s WHERE id=%s",
                (name, subject, body_markdown, id)
            )
        else:
            cur.execute(
                "INSERT INTO templates(name,subject,body_markdown) VALUES(%s,%s,%s)",
                (name, subject, body_markdown)
            )
        c.commit()
    return RedirectResponse(url="/dashboard/templates", status_code=303)


# ---------- UNS
