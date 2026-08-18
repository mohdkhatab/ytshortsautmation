import asyncio
import time
import random

import aiohttp

from logger import log
from db.database import create_task, update_task, get_task
from searcher.web_search import download_video_ytdlp
from searcher.reel_cache import get_search_results, ensure_cache
from ai_gen.content_gen import generate_content_with_ai, generate_content_from_prompt
from uploader.youtube_upload import upload_video, cleanup_files
import config


class TaskStatus:
    PENDING = "pending"
    SEARCHING = "searching"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    DOWNLOADING = "downloading"
    UPLOADING = "uploading"
    POLLING = "polling"
    COMPLETED = "completed"
    FAILED = "failed"


class AnimeUploadAgent:
    def __init__(self, telegram_app=None):
        self.telegram_app = telegram_app
        self.active_tasks: dict[int, asyncio.Task] = {}
        self.status_callbacks: dict[int, callable] = {}

    def set_status_callback(self, task_id: int, callback):
        self.status_callbacks[task_id] = callback

    async def _notify(self, task_id: int, message: str):
        cb = self.status_callbacks.get(task_id)
        if cb:
            try:
                await cb(message)
            except Exception:
                pass

    async def run_task(self, task_id: int, chat_id: int, custom_prompt: str = None) -> dict:
        log.info(f"[Task {task_id}] Starting automation task for chat {chat_id}")
        update_task(task_id, status=TaskStatus.SEARCHING)
        await self._notify(task_id, "📸 Instagram pe trending anime reels dhundh raha hoon...")

        try:
            async with aiohttp.ClientSession() as session:

                # Step 1: Get reels from cache (auto-refreshes if stale)
                log.info(f"[Task {task_id}] Step 1: Loading Instagram reels from cache")
                await self._notify(task_id, "📸 Instagram reels load ho rahe hain cache se...")
                await ensure_cache()
                search_results = get_search_results()

                ig_count = len(search_results.get("instagram", []))
                category = search_results.get("selected_category", "Unknown")

                update_task(task_id, status=TaskStatus.ANALYZING,
                           metadata={"category": category, "ig": ig_count})

                await self._notify(task_id,
                    f"📊 Results:\n"
                    f"📸 Instagram: {ig_count} reels loaded\n"
                    f"📂 Category: {category}")

                # Step 2: AI content generation
                log.info(f"[Task {task_id}] Step 2: Generating metadata with AI")
                await self._notify(task_id, "🤖 DeepSeek AI se title, description, tags generate kar raha hoon...")
                update_task(task_id, status=TaskStatus.GENERATING)

                if custom_prompt:
                    content = await generate_content_from_prompt(session, custom_prompt, search_results, task_id)
                else:
                    content = await generate_content_with_ai(session, search_results, task_id)

                update_task(task_id,
                           title=content["title"],
                           description=content["description"],
                           tags=",".join(content.get("tags", [])))

                await self._notify(task_id,
                    f"✅ Content Generated!\n\n"
                    f"📌 **Title:** {content['title']}\n"
                    f"📝 **Tags:** {', '.join(content.get('tags', [])[:8])}...")

                # Step 3: Download Instagram reel with yt-dlp
                log.info(f"[Task {task_id}] Step 3: Downloading Instagram reel with yt-dlp")
                await self._notify(task_id, "⬇️ yt-dlp se Instagram reel download kar raha hoon (premium quality)...")
                update_task(task_id, status=TaskStatus.DOWNLOADING)

                video_path = None
                video_url = None
                import random as rnd
                ig_reels = list(search_results.get("instagram", []))
                rnd.shuffle(ig_reels)

                for reel in ig_reels:
                    url = reel.get("url", "")
                    if not url:
                        continue
                    prefix = reel.get("caption", "")[:40] or "ig_reel"
                    log.info(f"[Task {task_id}] Trying: {url}")
                    path = await download_video_ytdlp(url, task_id, prefix)
                    if path:
                        video_path = path
                        video_url = url
                        break

                if not video_path:
                    update_task(task_id, status=TaskStatus.FAILED, error="No downloadable video found")
                    await self._notify(task_id, "❌ Koi downloadable video nahi mili.\nDobara try karo /start se")
                    return {"success": False, "error": "No downloadable video found"}

                update_task(task_id, source_url=video_url, video_path=video_path)

                await self._notify(task_id,
                    f"✅ Video Downloaded!\n"
                    f"🔗 Source: {video_url}\n"
                    f"📁 File: {video_path.split('/')[-1]}")

                # Step 4: Upload to YouTube Shorts API
                log.info(f"[Task {task_id}] Step 4: Uploading to YouTube Shorts API")
                await self._notify(task_id, "📤 YouTube Shorts API pe upload kar raha hoon...\nSource URL ya Base64 workflow use hoga")
                update_task(task_id, status=TaskStatus.UPLOADING)

                upload_result = await upload_video(
                    session, task_id, video_path, video_url,
                    content["title"], content["description"],
                    content.get("tags", []),
                    content.get("context", ""),
                )

                if upload_result.get("success"):
                    yt_url = upload_result.get("youtube_url", "")
                    status = upload_result.get("status", "processing")

                    update_task(task_id, status=TaskStatus.COMPLETED,
                               upload_url=yt_url or f"job:{upload_result.get('job_id', '')}")

                    await self._notify(task_id,
                        f"🎉 **UPLOAD SUCCESSFUL!**\n\n"
                        f"📌 **Title:** {content['title']}\n"
                        f"📂 **Category:** {category}\n"
                        f"🔗 **Source:** {video_url}\n"
                        f"📺 **YouTube:** {yt_url or 'Processing...'}\n"
                        f"📊 **Status:** {status.upper()}\n"
                        f"🆔 **Job ID:** {upload_result.get('job_id', 'N/A')}\n\n"
                        f"✅ Done! Naya task ke liye /start dabao!")

                    log.info(f"[Task {task_id}] SUCCESS! YouTube URL: {yt_url}")
                else:
                    error = upload_result.get("error", "Unknown error")
                    update_task(task_id, status=TaskStatus.FAILED, error=error)
                    await self._notify(task_id,
                        f"❌ **Upload Failed!**\n"
                        f"Error: {error}\n\n"
                        f"Retry ke liye /start dabao!")
                    log.error(f"[Task {task_id}] FAILED: {error}")

                # Cleanup downloaded file
                await cleanup_files(video_path)

                return {
                    "success": upload_result.get("success", False),
                    "task_id": task_id,
                    "title": content["title"],
                    "video_url": video_url,
                    "youtube_url": upload_result.get("youtube_url", ""),
                    "job_id": upload_result.get("job_id"),
                }

        except Exception as e:
            log.error(f"[Task {task_id}] Fatal error: {e}", exc_info=True)
            update_task(task_id, status=TaskStatus.FAILED, error=str(e))
            await self._notify(task_id, f"❌ **Error:** {str(e)[:200]}\n\nDobara try karo /start")
            return {"success": False, "error": str(e)}

    def start_task(self, chat_id: int, custom_prompt: str = None) -> int:
        task_id = create_task(chat_id, category="auto")
        log.info(f"New task created: {task_id} for chat {chat_id}")

        async def _run():
            try:
                await self.run_task(task_id, chat_id, custom_prompt)
            except Exception as e:
                log.error(f"Task {task_id} crashed: {e}")
            finally:
                self.active_tasks.pop(task_id, None)
                self.status_callbacks.pop(task_id, None)

        loop = asyncio.get_event_loop()
        task = loop.create_task(_run())
        self.active_tasks[task_id] = task
        return task_id

    def get_task_status(self, task_id: int) -> dict:
        return get_task(task_id) or {"error": "Task not found"}

    def cancel_task(self, task_id: int) -> bool:
        task = self.active_tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            update_task(task_id, status=TaskStatus.FAILED, error="Cancelled by user")
            return True
        return False
