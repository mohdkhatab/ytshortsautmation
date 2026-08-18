import asyncio
import base64
import json
import os
import uuid
from typing import Optional

import aiohttp

from logger import log
import config


def generate_request_id() -> str:
    return f"anime-{uuid.uuid4().hex[:12]}"


def get_auth_headers() -> dict:
    key = config.UPLOAD_API_KEY
    return {
        "Authorization": f"Bearer {key}" if not key.startswith("Bearer") else key,
        "Content-Type": "application/json",
    }


async def upload_via_source_url(session: aiohttp.ClientSession, task_id: int,
                                 video_url: str, title: str, description: str,
                                 tags: list[str], hashtags: list[str] = None,
                                 context: str = "") -> dict:
    """Upload using POST /api/automation/v1/jobs with a public HTTPS source URL."""
    request_id = generate_request_id()
    hashtags = hashtags or ["#Shorts", "#Anime"]

    payload = {
        "requestId": request_id,
        "source": {
            "url": video_url,
            "name": f"Anime edit - {title[:50]}",
            "approved": True,
            "rightsOwner": "Anime Upload Agent",
            "context": context or f"Anime editing video: {title}. Vertical short format for YouTube Shorts.",
        },
        "metadata": {
            "title": title[:100],
            "description": description[:4500],
            "hashtags": hashtags[:8],
            "tags": tags[:15],
        },
        "privacyStatus": "public",
        "maximumDurationSeconds": 60,
        "categoryId": "24",
    }

    log.info(f"[Task {task_id}] Posting job to API: {request_id}")
    log.debug(f"[Task {task_id}] Payload: {json.dumps(payload, indent=2)[:500]}")

    try:
        async with session.post(
            config.UPLOAD_API_URL,
            json=payload,
            headers=get_auth_headers(),
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            body = await resp.json()
            log.info(f"[Task {task_id}] Job response: {resp.status} | jobId={body.get('jobId')}")

            if resp.status in (200, 201):
                return {
                    "success": True,
                    "job_id": body.get("jobId"),
                    "request_id": request_id,
                    "status": body.get("status", "processing"),
                    "metadata_source": body.get("metadataSource", "caller"),
                }
            else:
                error = body.get("error", f"HTTP {resp.status}")
                log.error(f"[Task {task_id}] Job creation failed: {error}")
                return {"success": False, "error": error, "request_id": request_id}
    except Exception as e:
        log.error(f"[Task {task_id}] Job creation exception: {e}")
        return {"success": False, "error": str(e), "request_id": request_id}


async def upload_via_base64(session: aiohttp.ClientSession, task_id: int,
                             video_path: str, title: str, description: str,
                             tags: list[str], hashtags: list[str] = None,
                             context: str = "") -> dict:
    """Upload using POST /api/automation/v1/uploads with base64-encoded video.
    Max 30MB file size."""
    request_id = generate_request_id()
    hashtags = hashtags or ["#Shorts", "#Anime"]

    file_size = os.path.getsize(video_path)
    if file_size > 30 * 1024 * 1024:
        log.error(f"[Task {task_id}] File too large for base64: {file_size / 1024 / 1024:.1f}MB (max 30MB)")
        return {"success": False, "error": f"File too large: {file_size / 1024 / 1024:.1f}MB (max 30MB)"}

    if file_size == 0:
        return {"success": False, "error": "Empty file"}

    log.info(f"[Task {task_id}] Encoding video to base64 ({file_size / 1024 / 1024:.1f}MB)...")

    try:
        with open(video_path, "rb") as f:
            video_bytes = f.read()
        video_b64 = base64.b64encode(video_bytes).decode("ascii")
        del video_bytes

        filename = os.path.basename(video_path)
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska", ".mov": "video/quicktime"}
        mime_type = mime_map.get(ext, "video/mp4")

        payload = {
            "requestId": request_id,
            "video": {
                "fileName": filename,
                "mimeType": mime_type,
                "base64": video_b64,
            },
            "source": {
                "name": f"Anime edit - {title[:50]}",
                "approved": True,
                "rightsOwner": "Anime Upload Agent",
                "context": context or f"Anime editing video: {title}. Vertical short format for YouTube Shorts.",
            },
            "metadata": {
                "title": title[:100],
                "description": description[:4500],
                "hashtags": hashtags[:8],
                "tags": tags[:15],
            },
            "privacyStatus": "public",
            "maximumDurationSeconds": 60,
            "categoryId": "24",
        }

        del video_b64

        upload_url = f"{config.UPLOAD_API_BASE}/api/automation/v1/uploads"
        log.info(f"[Task {task_id}] Uploading base64 to API: {request_id}")

        async with session.post(
            upload_url,
            json=payload,
            headers=get_auth_headers(),
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp:
            body = await resp.json()
            log.info(f"[Task {task_id}] Upload response: {resp.status} | jobId={body.get('jobId')}")

            if resp.status in (200, 201):
                return {
                    "success": True,
                    "job_id": body.get("jobId"),
                    "request_id": request_id,
                    "status": body.get("status", "processing"),
                    "metadata_source": body.get("metadataSource", "caller"),
                }
            else:
                error = body.get("error", f"HTTP {resp.status}")
                log.error(f"[Task {task_id}] Upload failed: {error}")
                return {"success": False, "error": error, "request_id": request_id}
    except Exception as e:
        log.error(f"[Task {task_id}] Upload exception: {e}")
        return {"success": False, "error": str(e), "request_id": request_id}


async def poll_job_status(session: aiohttp.ClientSession, task_id: int,
                          job_id: int, max_wait: int = 300) -> dict:
    """Poll GET /api/automation/v1/jobs/{jobId} until uploaded or failed."""
    poll_url = f"{config.UPLOAD_API_BASE}/api/automation/v1/jobs/{job_id}"
    headers = {"Authorization": f"Bearer {config.UPLOAD_API_KEY}"}
    elapsed = 0
    interval = 5

    log.info(f"[Task {task_id}] Polling job {job_id} status...")

    while elapsed < max_wait:
        try:
            async with session.get(poll_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                body = await resp.json()
                job = body.get("job", {})
                status = job.get("status", "unknown")
                progress = job.get("progressPercent", 0)
                message = job.get("progressMessage", "")

                log.info(f"[Task {task_id}] Job {job_id}: {status} ({progress}%) - {message}")

                if status == "uploaded":
                    return {
                        "success": True,
                        "status": "uploaded",
                        "youtube_video_id": job.get("youtubeVideoId"),
                        "youtube_url": job.get("youtubeUrl"),
                        "progress": 100,
                    }
                elif status == "failed":
                    return {
                        "success": False,
                        "status": "failed",
                        "error": job.get("errorMessage", "Unknown failure"),
                    }
        except Exception as e:
            log.warning(f"[Task {task_id}] Poll error: {e}")

        await asyncio.sleep(interval)
        elapsed += interval
        interval = min(interval + 2, 15)

    return {"success": False, "status": "timeout", "error": f"Timed out after {max_wait}s"}


async def upload_video(session: aiohttp.ClientSession, task_id: int,
                       video_path: str, video_url: str,
                       title: str, description: str, tags: list[str],
                       context: str = "") -> dict:
    """Smart upload: try source URL first, fallback to base64."""
    hashtags = ["#Shorts", "#Anime", "#AnimeEdit"]
    for t in tags[:5]:
        tag = t.lower().replace(" ", "")
        if not tag.startswith("#"):
            tag = "#" + tag
        if len(tag) <= 30 and tag not in hashtags:
            hashtags.append(tag)
    hashtags = hashtags[:8]

    # Strategy 1: If video URL is YouTube/public HTTPS, try source URL job
    if video_url and video_url.startswith("https://") and "instagram.com" not in video_url:
        log.info(f"[Task {task_id}] Trying source URL workflow...")
        result = await upload_via_source_url(
            session, task_id, video_url, title, description, tags, hashtags, context
        )
        if result["success"] and result.get("job_id"):
            poll_result = await poll_job_status(session, task_id, result["job_id"])
            return {**result, **poll_result}
        log.info(f"[Task {task_id}] Source URL failed, falling back to base64...")

    # Strategy 2: Base64 direct upload (works for any downloaded file)
    file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
    if file_size > 30 * 1024 * 1024:
        return {"success": False, "error": f"File too large for upload: {file_size / 1024 / 1024:.1f}MB (max 30MB)"}

    log.info(f"[Task {task_id}] Using base64 upload workflow...")
    result = await upload_via_base64(
        session, task_id, video_path, title, description, tags, hashtags, context
    )
    if result["success"] and result.get("job_id"):
        poll_result = await poll_job_status(session, task_id, result["job_id"])
        return {**result, **poll_result}
    return result


async def cleanup_files(*paths):
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
                log.debug(f"Cleaned up: {p}")
            except Exception as e:
                log.warning(f"Failed to cleanup {p}: {e}")
