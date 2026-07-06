# URL Shortener Bot

An admin-only Telegram bot (Pyrogram/Kurigram) that shortens links into
`https://domain.app/{code}` and stores them in MongoDB. Visiting a
shortened link shows a white-background landing page that auto-redirects
after 5 seconds, with a green capsule "Open Link" button as a fallback.

## How it works

1. An admin (Telegram user ID in `ADMIN_IDS`) sends any `http(s)://` link
   to the bot in a private chat.
2. The bot generates a random short code (e.g. `A28UO`), saves
   `{code -> original_url}` in MongoDB, and replies with
   `https://domain.app/A28UO`.
3. When anyone opens that link, the aiohttp web server looks up the code
   in MongoDB and serves a landing page that redirects to the original
   URL after 5 seconds (via JS countdown + `<meta refresh>` fallback),
   with a green "Open Link" button in case the redirect doesn't fire.
4. Non-admins get "You are not authorized to use this bot." and cannot
   create links.

## Files

- `bot.py` — Pyrogram client, admin check, message handlers.
- `config.py` — reads all settings from environment variables.
- `db.py` — MongoDB (motor) access layer for storing/reading links.
- `shortener.py` — random code generation, URL validation, link creation.
- `webserver.py` — aiohttp server: health check + `/{code}` redirect route.
- `templates/redirect.html` — white background, green "Redirecting in 5
  seconds…" text, green capsule "Open Link" button.
- `templates/notfound.html` — shown when a code doesn't exist.

## Environment variables

See `.env.example`:

| Variable | Description |
|---|---|
| `API_ID` / `API_HASH` | From https://my.telegram.org |
| `BOT_TOKEN` | From @BotFather |
| `ADMIN_IDS` | Comma-separated Telegram user IDs allowed to use the bot |
| `MONGO_URI` | MongoDB connection string |
| `DB_NAME` | Database name (default `url_shortener`) |
| `BASE_URL` | Your public domain, e.g. `https://domain.app` (no trailing slash) |
| `SHORT_CODE_LENGTH` | Length of generated codes (default `6`) |

## Deploying on Koyeb

1. Push this repo to GitHub.
2. Create a Koyeb app from the repo (Dockerfile build).
3. Set all environment variables above in Koyeb's dashboard.
4. Point your domain (`domain.app`) to the Koyeb service.
5. The same aiohttp server (port 8080) handles both the Koyeb health
   check (`/health`) and the public redirect routes (`/{code}`), so no
   extra service is needed.

## Local run

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in values and export them
python bot.py
```
