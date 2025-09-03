# Cold Email Bot (Python)

A simple, compliant cold‑email sender with templating, throttling, and send logs (SQLite).

## Quick start

1) Create a virtualenv and install deps:
```
pip install -r requirements.txt
```

2) Copy env and fill in values:
```
cp .env.example .env
```

3) Add prospects to `prospects.csv` with columns like: `email,first_name,company,role`.

4) Dry run (no emails sent; logs as DRY_RUN):
```
python send.py --dry-run --limit 5
```

5) Send for real (respects throttling):
```
python send.py --limit 20 --template templates/email1.txt
```

- The bot will skip recipients already sent for the same template.
- Logs are saved to `sent_log.db` (SQLite).

## Deliverability checklist

- Use a custom domain with SPF, DKIM, DMARC aligned.
- Warm up the domain/ IP. Start with very low volume (e.g., 10–20/day).
- Add `List-Unsubscribe` headers and a visible opt‑out link in the body.
- Include your physical postal address.
- Personalise with relevant value; avoid spammy phrases and excessive links.
- Keep sending rate conservative (e.g., 1 every 30–60s at start).

## Sequences

You can schedule follow‑ups by running the bot again on a different day with `templates/followup1.txt`. The duplicate‑send guard is per template file name.

## Using an ESP

You can use SMTP creds from Mailgun, SendGrid, Amazon SES, Postmark, etc. For Gmail/Google Workspace, consider an ESP instead for cold outreach.
