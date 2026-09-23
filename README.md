# Telegram Channel Gate Bot

Sends anyone who DMs the bot a CAPTCHA image. Once they solve it, they get
a single-use invite link to your channel (it stops working after one
person uses it, so it can't be reposted or shared).

## 1. Create the bot
1. Open Telegram, message **@BotFather**.
2. Send `/newbot`, follow the prompts, choose a name and username.
3. BotFather gives you a token like `123456789:AAExample-Token`. Copy it.

## 2. Connect it to your channel
1. Open your channel's settings → **Administrators** → **Add Admin**.
2. Add your new bot.
3. Give it permission to **"Invite Users via Link"** (this is required —
   it's how the bot generates single-use links).
4. Find your channel's numeric ID:
   - Easiest way: forward any message from your channel to
     **@userinfobot** or **@JsonDumpBot** — it will show a `chat.id`
     field like `-1001234567890`. Use that exact value (including the
     minus sign) as `CHANNEL_ID`.
   - Alternative: if your channel has a public @username, you can use
     `@yourchannelusername` instead of the numeric ID.

## 3. Put this code on GitHub
1. Create a new repository on github.com (can be private).
2. Upload these five files: `bot.py`, `requirements.txt`,
   `render.yaml`, `.python-version`, `README.md`.
   - Easiest way if you're not using git commands: on the repo page,
     click **"Add file" → "Upload files"** and drag them in.

## 4. Deploy on Render (free)
1. Go to render.com, sign up / log in (you can use your GitHub account).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub account if prompted, then select the repo you
   just created. Render will read `render.yaml` automatically and
   set this up as a **Web Service** on the free tier.
4. When asked, fill in the two environment variables:
   - `BOT_TOKEN` → the token from BotFather
   - `CHANNEL_ID` → the numeric ID (or @username) from step 2
5. Click **Apply** / **Deploy**. Render will install dependencies and
   start the bot. Once it's live, copy the `.onrender.com` URL Render
   gives your service — you'll need it for step 5.

## 5. Keep it awake with UptimeRobot (free)
Render's free Web Services fall asleep after 15 minutes with no
traffic, and take 30-50 seconds to wake back up on the next request.
UptimeRobot pings your service regularly so it never falls asleep.

1. Go to uptimerobot.com, sign up for a free account.
2. Click **+ Add New Monitor**.
3. Monitor Type: **HTTP(s)**.
4. Friendly Name: anything, e.g. "Telegram gate bot".
5. URL: paste the `.onrender.com` URL from step 4 above.
6. Monitoring Interval: 5 minutes (the shortest free option — well
   under Render's 15-minute sleep window).
7. Click **Create Monitor**.

That's it — UptimeRobot will now hit your bot's health-check endpoint
every 5 minutes, which keeps Render from putting it to sleep.

## 6. Test it
1. Open Telegram, search for your bot's username, tap **Start**.
2. It should send you a distorted code image.
3. Reply with the code. You should get back a one-time invite link.
4. Open that link in a different Telegram account (or ask a friend) to
   confirm it works — and that reusing the same link afterward fails.

## Notes
- **Free tier behavior:** even with UptimeRobot pinging it, there's a
  small chance of an occasional slow first response if a ping is
  missed or Render has a hiccup. This is a free-tier tradeoff, not a
  bug in the bot.
- **The health-check server:** `bot.py` runs a tiny built-in web
  server alongside the bot purely so Render has a port to detect and
  UptimeRobot has something to ping. It doesn't do anything else —
  all the actual bot logic is still the CAPTCHA + invite-link flow.
- **Retries:** a user gets 5 attempts per CAPTCHA before the bot sends
  a fresh code automatically. You can change `MAX_ATTEMPTS_PER_ROUND`
  at the top of `bot.py` if you want that looser or stricter.
- **Rotating the bot token:** if the token ever leaks, message
  @BotFather → `/revoke` to invalidate it and issue a new one, then
  update `BOT_TOKEN` in Render's environment variable settings (no
  code change needed).
- Nothing in this code needs edits based on your specific channel —
  all the channel-specific values live in the two environment
  variables, not in the code.
