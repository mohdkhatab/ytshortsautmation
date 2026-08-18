import asyncio
import random
import json
import os
import re
from typing import Optional
import aiohttp
from bs4 import BeautifulSoup

from logger import log
import config


ANIME_SOURCES = [
    {"name": "Naruto", "hashtags": ["narutoedit", "narutoamv", "narutoeditz", "borutoedit"],
     "keywords": ["naruto shippuden edit", "naruto amv", "boruto edit"]},
    {"name": "Dragon Ball", "hashtags": ["dragonballz", "dragonball", "gokuedit", "vegetaedit"],
     "keywords": ["dragon ball edit", "goku amv", "vegeta edit"]},
    {"name": "One Piece", "hashtags": ["onepieceedit", "luffyedit", "onepieceamv"],
     "keywords": ["one piece edit", "luffy edit"]},
    {"name": "Jujutsu Kaisen", "hashtags": ["jujutsukaisen", "gojoedit", "jjkedit"],
     "keywords": ["jujutsu kaisen edit", "gojo edit"]},
    {"name": "Attack on Titan", "hashtags": ["attackontitan", "aotedit", "erenedit"],
     "keywords": ["attack on titan edit", "eren edit"]},
    {"name": "Chinese Anime", "hashtags": ["donghua", "chineseanime", "donghuaedit"],
     "keywords": ["donghua edit", "chinese anime edit"]},
    {"name": "Demon Slayer", "hashtags": ["demonslayer", "tanjiroedit"],
     "keywords": ["demon slayer edit", "tanjiro edit"]},
    {"name": "Indian Anime Edit", "hashtags": ["indiananime", "hindianime", "animeindia"],
     "keywords": ["indian anime edit", "hindi anime edit"]},
    {"name": "Anime Mix", "hashtags": ["animeedit", "animeedits", "animeviral", "amv"],
     "keywords": ["anime mix edit", "anime compilation"]},
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def search_instagram_via_google(session: aiohttp.ClientSession, query: str, max_results: int = 10) -> list[dict]:
    """Search Google for Instagram reels - most reliable method."""
    results = []
    try:
        url = "https://www.google.com/search"
        params = {"q": f"site:instagram.com/reel {query}", "num": max_results}
        headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()

        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "instagram.com/reel/" in href or "instagram.com/p/" in href:
                if "/url?q=" in href:
                    href = href.split("/url?q=")[1].split("&")[0]
                shortcode = href.rstrip("/").split("/")[-1]
                if shortcode and len(shortcode) > 5 and shortcode not in [r.get("shortcode") for r in results]:
                    caption_el = a.find("span") or a.find("div")
                    caption = caption_el.get_text(strip=True)[:200] if caption_el else query
                    results.append({
                        "source": "instagram",
                        "shortcode": shortcode,
                        "url": f"https://www.instagram.com/reel/{shortcode}/",
                        "web_url": href,
                        "caption": caption,
                        "is_video": True,
                    })
        log.info(f"Instagram Google search for '{query}': found {len(results)} reels")
    except Exception as e:
        log.warning(f"Instagram Google search failed: {e}")
    return results[:max_results]


async def search_instagram_via_duckduckgo(session: aiohttp.ClientSession, query: str, max_results: int = 10) -> list[dict]:
    """Search DuckDuckGo for Instagram reels with retry."""
    results = []
    queries = [
        f"site:instagram.com/reel {query}",
        f"instagram reel {query}",
        f"{query} instagram reel anime",
    ]
    for q in queries:
        if results:
            break
        for attempt in range(2):
            try:
                url = "https://html.duckduckgo.com/html/"
                data = {"q": q, "kl": "us-en"}
                headers = {"User-Agent": UA}
                async with session.post(url, data=data, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    html = await resp.text()

                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", class_="result__a", href=True):
                    href = a["href"]
                    if "instagram.com" in href:
                        shortcode = href.rstrip("/").split("/")[-1]
                        if shortcode and len(shortcode) > 5:
                            results.append({
                                "source": "instagram",
                                "shortcode": shortcode,
                                "url": f"https://www.instagram.com/reel/{shortcode}/",
                                "web_url": href,
                                "caption": a.get_text(strip=True)[:200],
                                "is_video": True,
                            })
                if results:
                    break
                await asyncio.sleep(2 * (attempt + 1))
            except Exception as e:
                log.warning(f"DDG attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2)

    log.info(f"Instagram DDG search for '{query}': found {len(results)} reels")
    return results[:max_results]


async def search_youtube_videos(session: aiohttp.ClientSession, query: str, max_results: int = 5) -> list[dict]:
    results = []
    try:
        search_url = "https://www.youtube.com/results"
        params = {"search_query": query, "sp": "EgIQAQ%3D%3D"}
        async with session.get(search_url, params=params, headers={"User-Agent": UA}, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script"):
            text = script.string or ""
            if "var ytInitialData" in text:
                data_str = text.split("var ytInitialData = ", 1)[1].rstrip(";")
                data = json.loads(data_str)
                contents = (data.get("contents", {})
                           .get("twoColumnSearchResultsRenderer", {})
                           .get("primaryContents", {})
                           .get("sectionListRenderer", {})
                           .get("contents", []))
                for section in contents:
                    items = section.get("itemSectionRenderer", {}).get("contents", [])
                    for item in items[:max_results]:
                        vid = item.get("videoRenderer")
                        if not vid:
                            continue
                        results.append({
                            "source": "youtube",
                            "title": vid.get("title", {}).get("runs", [{}])[0].get("text", ""),
                            "url": "https://www.youtube.com/watch?v=" + vid.get("videoId", ""),
                            "video_id": vid.get("videoId", ""),
                            "channel": vid.get("ownerText", {}).get("runs", [{}])[0].get("text", ""),
                            "views": vid.get("viewCountText", {}).get("simpleText", ""),
                            "duration": vid.get("lengthText", {}).get("simpleText", ""),
                        })
                break
    except Exception as e:
        log.warning(f"YouTube search failed: {e}")
    return results[:max_results]


async def search_trending_anime_content(session: aiohttp.ClientSession) -> dict:
    log.info("Starting search...")
    category = random.choice(ANIME_SOURCES)
    keyword = random.choice(category["keywords"])
    hashtag = random.choice(category["hashtags"])

    results = {"instagram": [], "youtube": [], "selected_category": category["name"], "keyword": keyword}

    # Instagram search via multiple engines
    ig_g = await search_instagram_via_google(session, f"{keyword} reel", max_results=8)
    ig_d = await search_instagram_via_duckduckgo(session, f"{keyword} reel", max_results=5)
    ig_d2 = await search_instagram_via_duckduckgo(session, f"anime edit instagram reel", max_results=5)
    results["instagram"] = ig_g + ig_d + ig_d2

    # Dedup
    seen = set()
    unique = []
    for r in results["instagram"]:
        sc = r.get("shortcode", "")
        if sc and sc not in seen:
            seen.add(sc)
            unique.append(r)
    results["instagram"] = unique
    log.info(f"Instagram total: {len(results['instagram'])} unique reels")

    # YouTube (for search/reference only)
    yt = await search_youtube_videos(session, f"{keyword} edit", max_results=5)
    results["youtube"] = yt
    log.info(f"YouTube: {len(yt)} videos")

    total = len(results["instagram"]) + len(results["youtube"])
    log.info(f"Search done: {total} sources [{category['name']}]")
    return results


async def download_video_ytdlp(url: str, task_id: int, filename_prefix: str = "") -> Optional[str]:
    import yt_dlp

    safe_name = re.sub(r'[^\w\s-]', '', filename_prefix)[:40].strip() or "video"
    outtmpl = str(config.DOWNLOAD_DIR / f"task_{task_id}_{safe_name}_%(id)s.%(ext)s")

    def _download():
        opts = {
            "format": "best[height<=720][ext=mp4]/best[height<=720]/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "noplaylist": True,
            "socket_timeout": 60,
            "retries": 3,
            "http_headers": {"User-Agent": UA},
            # Workaround for bot detection
            "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
            "geo_bypass": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info), info

    try:
        loop = asyncio.get_event_loop()
        filename, info = await loop.run_in_executor(None, _download)

        actual = filename
        if not os.path.exists(actual):
            base = os.path.splitext(actual)[0]
            for ext in (".mp4", ".webm", ".mkv", ".mov"):
                if os.path.exists(base + ext):
                    actual = base + ext
                    break

        if os.path.exists(actual):
            size = os.path.getsize(actual)
            if size <= config.MAX_FILE_SIZE:
                log.info(f"Downloaded: {actual} ({size / 1024 / 1024:.1f}MB)")
                return actual
            else:
                os.remove(actual)
                log.warning(f"File too large: {size / 1024 / 1024:.1f}MB")
                return None
    except Exception as e:
        log.error(f"yt-dlp failed for {url}: {e}")
    return None


async def download_best_video(session: aiohttp.ClientSession, search_results: dict, task_id: int) -> Optional[tuple]:
    """Download best video. Priority: Instagram > YouTube."""
    # Priority 1: Instagram reels (yt-dlp handles these great)
    ig_videos = [v for v in search_results.get("instagram", []) if v.get("url")]
    random.shuffle(ig_videos)
    for v in ig_videos:
        url = v.get("url", "")
        prefix = v.get("caption", "")[:40] or "ig_reel"
        log.info(f"[Task {task_id}] Trying Instagram: {url}")
        path = await download_video_ytdlp(url, task_id, prefix)
        if path:
            return path, url

    # Priority 2: YouTube (may fail on servers due to bot detection)
    yt_videos = search_results.get("youtube", [])
    random.shuffle(yt_videos)
    for v in yt_videos:
        url = v.get("url", "")
        if not url:
            continue
        prefix = v.get("title", "")[:40] or "yt_video"
        log.info(f"[Task {task_id}] Trying YouTube: {url}")
        path = await download_video_ytdlp(url, task_id, prefix)
        if path:
            return path, url

    return None
