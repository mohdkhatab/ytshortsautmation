import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from logger import log
from config import BOT_TOKEN
from bot.telegram_bot import start_cmd, status_cmd, tasks_cmd, cancel_cmd, callback_handler
from scheduler import scheduler
from health_server import start_health_server


async def run():
    # 1. Start health web server IMMEDIATELY for Render port binding
    await start_health_server()

    # 2. Build Telegram Application
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("tasks", tasks_cmd))
    application.add_handler(CommandHandler("cancel", cancel_cmd))
    application.add_handler(CallbackQueryHandler(callback_handler))

    # 3. Initialize application & start scheduler
    await application.initialize()
    scheduler.set_bot(application.bot)
    scheduler.start()
    asyncio.create_task(scheduler._scheduler_loop())

    log.info("Bot + Auto Scheduler + Health API all running!")
    log.info("Auto upload: Har 30 min pe Instagram reel -> YouTube Shorts")

    # 4. Start polling
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram Polling active! Send /start in Telegram.")

    # 5. Keep alive indefinitely
    stop_event = asyncio.Event()
    await stop_event.wait()

    await application.updater.stop()
    await application.stop()
    await application.shutdown()


if __name__ == "__main__":
    log.info("Starting Anime Upload Agent (Bot + Auto Scheduler)...")
    asyncio.run(run())
