import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from telegram import Bot
from telegram.helpers import escape_markdown

from logger import log
from agent.orchestrator import AnimeUploadAgent, TaskStatus
from db.database import create_task, update_task, get_task
from ai_gen.content_gen import generate_content_with_ai
from searcher.reel_cache import get_search_results, ensure_cache
from searcher.web_search import download_video_ytdlp
from uploader.youtube_upload import upload_video, cleanup_files
import config

IST = ZoneInfo("Asia/Kolkata")

agent = AnimeUploadAgent()


def _md(text) -> str:
    """Escape dynamic text for Telegram legacy Markdown to avoid parse errors."""
    return escape_markdown(str(text), version=1)


class AutoScheduler:
    def __init__(self):
        self.bot: Bot = None
        self.running = False
        self.interval_minutes = 30

    def set_bot(self, bot: Bot):
        self.bot = bot

    async def _notify(self, chat_id: int, text: str):
        if self.bot:
            try:
                await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            except Exception as e:
                log.warning(f"Auto-notify failed: {e}")

    async def _run_single_upload(self):
        chat_ids = config.ALLOWED_USERS
        if not chat_ids:
            log.warning("No ALLOWED_USERS set, skipping auto upload")
            return

        now = datetime.now(IST)
        log.info(f"[AutoUpload] Starting at {now.strftime('%H:%M IST')}")

        for chat_id in chat_ids:
            await self._notify(chat_id,
                f"🤖 **Auto Upload Started!**\n"
                f"⏰ Time: {now.strftime('%I:%M %p IST')}\n"
                f"🔄 Har 30 min pe ek reel upload hoga...\n\n"
                f"📸 Instagram se search ho raha hai...")

        task_id = create_task(
            chat_id=chat_ids[0],
            category="Auto Upload",
        )
        update_task(task_id, status=TaskStatus.SEARCHING)

        try:
            async with aiohttp.ClientSession() as session:

                # Step 1: Search
                log.info(f"[AutoUpload Task {task_id}] Step 1: Loading reels from cache")
                await ensure_cache()
                search_results = get_search_results()

                ig_count = len(search_results.get("instagram", []))
                category = search_results.get("selected_category", "Unknown")
                update_task(task_id, status=TaskStatus.ANALYZING,
                           metadata={"category": category, "ig": ig_count})

                for chat_id in chat_ids:
                    await self._notify(chat_id,
                        f"📸 **{ig_count} reels mil gaye!**\n"
                        f"📂 Category: {_md(category)}\n"
                        f"🤖 AI se title/description bana raha hoon...")

                # Step 2: AI Generation
                log.info(f"[AutoUpload Task {task_id}] Step 2: Generating metadata with AI")
                update_task(task_id, status=TaskStatus.GENERATING)
                content = await generate_content_with_ai(session, search_results, task_id)
                title = content.get("title", "Anime Edit #Shorts")
                description = content.get("description", "Anime compilation #Shorts")
                tags = content.get("tags", ["anime", "animeedit", "shorts"])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                context = content.get("context", "")

                update_task(task_id, title=title, tags=tags)

                for chat_id in chat_ids:
                    await self._notify(chat_id,
                        f"🤖 **AI Content Ready:**\n"
                        f"📌 Title: {_md(title)}\n"
                        f"🏷️ Tags: {_md(', '.join(tags[:5]))}\n"
                        f"⬇️ Downloading reel...")

                # Step 3: Download
                log.info(f"[AutoUpload Task {task_id}] Step 3: Downloading Instagram reel")
                update_task(task_id, status=TaskStatus.DOWNLOADING)
                import random
                ig_reels = list(search_results.get("instagram", []))
                random.shuffle(ig_reels)

                video_path = None
                video_url = None
                for reel in ig_reels:
                    url = reel.get("url", "")
                    if not url:
                        continue
                    prefix = reel.get("caption", "")[:40] or "ig_reel"
                    path = await download_video_ytdlp(url, task_id, prefix)
                    if path:
                        video_path = path
                        video_url = url
                        break

                if not video_path:
                    update_task(task_id, status=TaskStatus.FAILED, error="Download failed")
                    for chat_id in chat_ids:
                        await self._notify(chat_id, "❌ Auto upload failed: Download nahi ho paya.\nRetry hoga next 30 min mein.")
                    return

                import os
                file_size = os.path.getsize(video_path)
                update_task(task_id, source_url=video_url, video_path=video_path)

                for chat_id in chat_ids:
                    await self._notify(chat_id,
                        f"✅ **Video Downloaded!**\n"
                        f"📁 Size: {file_size/1024/1024:.1f}MB\n"
                        f"📤 YouTube pe upload ho raha hai...")

                # Step 4: Upload
                log.info(f"[AutoUpload Task {task_id}] Step 4: Uploading to YouTube Shorts API")
                update_task(task_id, status=TaskStatus.UPLOADING)

                upload_result = await upload_video(
                    session, task_id, video_path, video_url,
                    title, description, tags, context,
                )

                if upload_result.get("success"):
                    youtube_url = upload_result.get("youtube_url", "")
                    update_task(task_id, status=TaskStatus.COMPLETED, upload_url=youtube_url)

                    for chat_id in chat_ids:
                        await self._notify(chat_id,
                            f"🎉 **AUTO UPLOAD SUCCESS!**\n\n"
                            f"📌 Title: {_md(title)}\n"
                            f"🔗 YouTube: {_md(youtube_url)}\n"
                            f"📸 Source: {_md(video_url)}\n"
                            f"⏰ Next upload: 30 min baad\n\n"
                            f"🤖 Auto upload continue rahega!")
                else:
                    error = upload_result.get("error", "Unknown error")
                    update_task(task_id, status=TaskStatus.FAILED, error=error)

                    for chat_id in chat_ids:
                        await self._notify(chat_id,
                            f"❌ **Upload Failed:** {_md(error)}\n"
                            f"🔄 Next upload: 30 min baad try hoga")

                cleanup_files(video_path)

        except Exception as e:
            log.error(f"[AutoUpload Task {task_id}] Error: {e}", exc_info=True)
            update_task(task_id, status=TaskStatus.FAILED, error=str(e))
            for chat_id in chat_ids:
                await self._notify(chat_id,
                    f"❌ **Auto Upload Error:** {_md(str(e)[:200])}\n"
                    f"🔄 Next upload: 30 min baad try hoga")

    async def _scheduler_loop(self):
        log.info("[Scheduler] Auto upload scheduler started!")
        log.info(f"[Scheduler] Uploading every {self.interval_minutes} minutes (IST aligned)")

        while self.running:
            now = datetime.now(IST)
            current_min = now.minute
            next_min = (current_min // 30 + 1) * 30
            if next_min >= 60:
                next_wait = timedelta(
                    hours=1,
                    minutes=0,
                    seconds=0,
                    microseconds=0,
                ) - timedelta(minutes=current_min, seconds=now.second, microseconds=now.microsecond)
            else:
                next_wait = timedelta(minutes=next_min - current_min, seconds=now.second, microseconds=now.microsecond)

            next_time = now + next_wait
            log.info(f"[Scheduler] Next upload at {next_time.strftime('%I:%M %p IST')} ({int(next_wait.total_seconds())}s wait)")

            await asyncio.sleep(next_wait.total_seconds())

            if self.running:
                await self._run_single_upload()

    def start(self):
        self.running = True

    def stop(self):
        self.running = False
        log.info("[Scheduler] Scheduler stopped")


scheduler = AutoScheduler()
