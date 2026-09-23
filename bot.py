"""
Telegram channel gatekeeper bot.

Flow:
  1. A user DMs the bot (/start).
  2. The bot generates a random code, renders it as a distorted image
     (a basic CAPTCHA), and sends it to the user.
  3. The user replies with the text they see in the image.
  4. If it matches, the bot creates a fresh, single-use (member_limit=1)
     invite link to the channel and sends it to the user. That link
     stops working after one person joins through it, so it can't be
     shared or reposted publicly.
  5. If it doesn't match, the bot sends a new CAPTCHA and lets them try
     again (with a small limit on retries so nobody can hammer it).

Environment variables required (set these in Render, never in the code):
  BOT_TOKEN    - the token from @BotFather
  CHANNEL_ID   - the channel's numeric ID (e.g. -1001234567890) OR
                 its @username if the channel is public
"""

import asyncio
import logging
import os
import random
import string
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

MAX_ATTEMPTS_PER_ROUND = 5  # how many wrong guesses before a fresh code is forced
CODE_LENGTH = 5
CODE_ALPHABET = string.ascii_uppercase + string.digits
# Characters that look alike are excluded to keep the CAPTCHA fair, not just hard.
CODE_ALPHABET = CODE_ALPHABET.translate(str.maketrans("", "", "0O1IL"))


def generate_code(length: int = CODE_LENGTH) -> str:
    return "".join(random.choice(CODE_ALPHABET) for _ in range(length))


def render_captcha(code: str) -> BytesIO:
    """Render `code` as a distorted image and return it as PNG bytes in memory."""
    width, height = 260, 100
    background = (245, 245, 245)
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    # Try a bundled truetype font first; fall back to PIL's default bitmap font
    # if none is available in the deployment environment.
    font = None
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if os.path.exists(candidate):
            font = ImageFont.truetype(candidate, 48)
            break
    if font is None:
        font = ImageFont.load_default()

    # Background noise lines, drawn first so the text sits on top of them.
    for _ in range(6):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(180, 180, 180), width=2)

    # Draw each character with a random vertical offset and rotation so the
    # code can't be lifted with plain OCR.
    x_cursor = 15
    for ch in code:
        char_img = Image.new("RGBA", (60, 70), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        color = (
            random.randint(20, 90),
            random.randint(20, 90),
            random.randint(20, 90),
        )
        char_draw.text((5, 5), ch, font=font, fill=color)
        angle = random.randint(-25, 25)
        char_img = char_img.rotate(angle, expand=1, resample=Image.BICUBIC)
        y_offset = random.randint(10, 30)
        image.paste(char_img, (x_cursor, y_offset), char_img)
        x_cursor += 42

    # Speckle noise dots on top.
    for _ in range(200):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        draw.point((x, y), fill=(random.randint(150, 200),) * 3)

    image = image.filter(ImageFilter.SMOOTH)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def send_new_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    code = generate_code()
    context.user_data["pending_code"] = code
    context.user_data["attempts"] = 0
    image_buffer = render_captcha(code)
    await update.effective_chat.send_photo(
        photo=image_buffer,
        caption=(
            "Type the letters/numbers you see in the image above and send "
            "them back to me to get the channel invite link."
        ),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_chat.send_message(
        "Hi! To get the invite link, solve the quick check below."
    )
    await send_new_captcha(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending_code = context.user_data.get("pending_code")

    if not pending_code:
        # No CAPTCHA in progress for this user yet — start one.
        await update.effective_chat.send_message(
            "Let's get you verified first."
        )
        await send_new_captcha(update, context)
        return

    user_answer = (update.message.text or "").strip().upper()

    if user_answer == pending_code:
        context.user_data.pop("pending_code", None)
        context.user_data.pop("attempts", None)
        await grant_access(update, context)
        return

    context.user_data["attempts"] = context.user_data.get("attempts", 0) + 1

    if context.user_data["attempts"] >= MAX_ATTEMPTS_PER_ROUND:
        await update.effective_chat.send_message(
            "That didn't match, and you've hit the retry limit for this "
            "code. Here's a fresh one."
        )
        await send_new_captcha(update, context)
    else:
        remaining = MAX_ATTEMPTS_PER_ROUND - context.user_data["attempts"]
        await update.effective_chat.send_message(
            f"That doesn't match. Try again (case doesn't matter) — "
            f"{remaining} attempt(s) left before I send a new code."
        )


async def grant_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            name=f"gate-{update.effective_user.id}",
        )
    except Exception as exc:  # noqa: BLE001 - log and tell the user plainly
        logger.exception("Failed to create invite link")
        await update.effective_chat.send_message(
            "Something went wrong generating your invite link. Please try "
            "again in a moment, or contact the channel owner directly."
        )
        return

    await update.effective_chat.send_message(
        "Verified! Here's your one-time invite link — it only works once, "
        f"so don't share it:\n\n{invite_link.invite_link}"
    )


class _HealthCheckHandler(BaseHTTPRequestHandler):
    """Bare-bones HTTP handler so Render sees an open port and UptimeRobot
    has something to ping. Has nothing to do with the bot logic itself."""

    def do_GET(self):  # noqa: N802 - name required by BaseHTTPRequestHandler
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):  # noqa: A002 - silence default logging
        pass  # keep Render's logs focused on the bot, not ping traffic


def start_health_check_server() -> None:
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    logger.info("Health check server listening on port %s", port)
    server.serve_forever()


def main() -> None:
    # Python 3.14 no longer auto-creates an event loop in the main thread,
    # which python-telegram-bot's run_polling() relies on internally.
    # Create and set one explicitly before calling it.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run the tiny HTTP server in a background thread so it doesn't block
    # the bot's polling loop, and vice versa.
    threading.Thread(target=start_health_check_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Bot starting (polling mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
