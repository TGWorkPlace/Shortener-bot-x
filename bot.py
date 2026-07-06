import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_IDS
from webserver import run_webserver
import db
from shortener import create_short_link, is_valid_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BroadcastBot(Client):
    def __init__(self):
        super().__init__(
            name="broadcast_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
        )

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        me = await self.get_me()
        logger.info(f"Bot started: @{me.username}")

        await db.connect()

        self._web_runner = await run_webserver()

    async def stop(self, *args, **kwargs):
        if hasattr(self, "_web_runner"):
            await self._web_runner.cleanup()
        await db.close()
        await super().stop(*args, **kwargs)
        logger.info("Bot stopped.")


app = BroadcastBot()


def is_admin(_, __, message: Message) -> bool:
    return bool(message.from_user) and message.from_user.id in ADMIN_IDS


admin_filter = filters.create(is_admin)


@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("You are not authorized to use this bot.")
        return

    await message.reply(
        "Hi! Send me any link and I'll shorten it for you.\n\n"
        "Example:\nhttps://example.com/XXXX"
    )


@app.on_message(filters.private & filters.text & ~filters.command("start") & admin_filter)
async def shorten_link_handler(client: Client, message: Message):
    text = message.text.strip()

    if not is_valid_url(text):
        await message.reply(
            "That doesn't look like a valid link. Please send a full URL, "
            "starting with http:// or https://"
        )
        return

    try:
        short_url = await create_short_link(text, message.from_user.id)
    except Exception as e:
        logger.exception("Failed to create short link")
        await message.reply(f"Something went wrong while shortening your link: {e}")
        return

    await message.reply(
        f"Here's your shortened link:\n{short_url}",
        disable_web_page_preview=True,
    )


@app.on_message(filters.private & filters.text & ~admin_filter)
async def unauthorized_handler(client: Client, message: Message):
    await message.reply("You are not authorized to use this bot.")


if __name__ == "__main__":
    app.run()
