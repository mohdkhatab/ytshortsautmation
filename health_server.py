import asyncio
import os
from aiohttp import web

from logger import log


async def health_handler(request):
    return web.json_response({
        "status": "ok",
        "service": "anime-upload-bot",
        "message": "Bot is running!",
    })


async def start_health_server():
    port = int(os.getenv("PORT", "8080"))
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Health API running on http://0.0.0.0:{port}/health")
