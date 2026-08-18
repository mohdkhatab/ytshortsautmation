import asyncio
from aiohttp import web

from logger import log


async def health_handler(request):
    return web.json_response({
        "status": "ok",
        "service": "anime-upload-bot",
        "message": "Bot is running!",
    })


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    log.info("Health API running on http://0.0.0.0:8080/health")
