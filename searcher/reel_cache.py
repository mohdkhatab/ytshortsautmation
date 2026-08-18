import asyncio
import json
import random
import os
import re
import time
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

from logger import log
import config


CACHE_FILE = config.BASE_DIR / "reel_cache.json"
CACHE_MAX_AGE = 3600  # 1 hour

ANIME_CATEGORIES = [
    {"name": "Naruto", "queries": ["naruto anime edit reel", "naruto amv instagram", "naruto edit viral"]},
    {"name": "Dragon Ball", "queries": ["dragon ball edit reel", "goku amv instagram", "vegeta edit viral"]},
    {"name": "One Piece", "queries": ["one piece edit reel", "luffy amv instagram", "one piece viral"]},
    {"name": "Jujutsu Kaisen", "queries": ["jujutsu kaisen edit reel", "gojo edit instagram", "jjk amv"]},
    {"name": "Attack on Titan", "queries": ["attack on titan edit reel", "eren edit instagram", "aot amv"]},
    {"name": "Chinese Anime", "queries": ["donghua edit reel", "chinese anime instagram", "donghua amv"]},
    {"name": "Demon Slayer", "queries": ["demon slayer edit reel", "tanjiro edit instagram", "kimetsu edit"]},
    {"name": "Indian Anime Edit", "queries": ["indian anime edit reel", "hindi anime instagram"]},
    {"name": "Anime Mix", "queries": ["anime edit reel viral", "anime amv instagram", "anime fan edit"]},
]


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text())
            if time.time() - data.get("timestamp", 0) < CACHE_MAX_AGE:
                return data
        except Exception:
            pass
    return {"timestamp": 0, "reels": {}}


def save_cache(data: dict):
    data["timestamp"] = time.time()
    CACHE_FILE.write_text(json.dumps(data, indent=2))


async def fetch_reels_from_ddg(session: aiohttp.ClientSession, query: str) -> list[dict]:
    """Fetch Instagram reel URLs from DuckDuckGo HTML search."""
    results = []
    try:
        url = "https://html.duckduckgo.com/html/"
        payload = {"q": f"site:instagram.com/reel {query}", "kl": "us-en"}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        async with session.post(url, data=payload, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()

        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", class_="result__a", href=True):
            href = a["href"]
            if "instagram.com" in href:
                shortcode = href.rstrip("/").split("/")[-1]
                if shortcode and len(shortcode) > 5:
                    caption_el = a.find("span") or a.find("div")
                    caption = caption_el.get_text(strip=True)[:200] if caption_el else query
                    results.append({
                        "source": "instagram",
                        "shortcode": shortcode,
                        "url": f"https://www.instagram.com/reel/{shortcode}/",
                        "caption": caption,
                        "is_video": True,
                    })
    except Exception as e:
        log.warning(f"DDG fetch failed for '{query}': {e}")
    return results


async def fetch_reels_from_yandex(session: aiohttp.ClientSession, query: str) -> list[dict]:
    """Fetch from Yandex as backup."""
    results = []
    try:
        url = "https://yandex.com/search/"
        params = {"text": f"site:instagram.com/reel {query}", "lr": 84}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        async with session.get(url, params=params, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()

        shortcodes = list(set(re.findall(r"instagram\.com/(?:reel|p)/([A-Za-z0-9_-]+)", html)))
        for sc in shortcodes:
            if len(sc) > 5:
                results.append({
                    "source": "instagram",
                    "shortcode": sc,
                    "url": f"https://www.instagram.com/reel/{sc}/",
                    "caption": query,
                    "is_video": True,
                })
    except Exception as e:
        log.warning(f"Yandex fetch failed: {e}")
    return results


async def refresh_cache():
    """Refresh the reel URL cache from search engines."""
    log.info("Refreshing reel cache from search engines...")
    cache = load_cache()

    async with aiohttp.ClientSession() as session:
        for cat in ANIME_CATEGORIES:
            query = random.choice(cat["queries"])
            reels = await fetch_reels_from_ddg(session, query)
            if not reels:
                reels = await fetch_reels_from_yandex(session, query)

            if reels:
                cache["reels"][cat["name"]] = reels
                log.info(f"Cache[{cat['name']}]: {len(reels)} reels from '{query}'")
            else:
                log.warning(f"Cache[{cat['name']}]: 0 reels from '{query}'")

            await asyncio.sleep(2)

    save_cache(cache)
    total = sum(len(v) for v in cache["reels"].values())
    log.info(f"Cache refreshed: {total} total reels across {len(cache['reels'])} categories")
    return cache


def get_random_reel(category: str = None) -> dict | None:
    """Get a random reel URL from cache. Returns None if cache is empty."""
    cache = load_cache()
    reels = cache.get("reels", {})

    if category and category in reels and reels[category]:
        return random.choice(reels[category])

    # Any category
    all_reels = []
    for cat_reels in reels.values():
        all_reels.extend(cat_reels)

    if all_reels:
        return random.choice(all_reels)
    return None


def get_search_results(category: str = None) -> dict:
    """Get search results in the format expected by the orchestrator."""
    cache = load_cache()
    reels = cache.get("reels", {})

    selected = category or random.choice(list(reels.keys())) if reels else "Anime Mix"
    cat_reels = reels.get(selected, reels.get("Anime Mix", []))

    return {
        "instagram": cat_reels,
        "youtube": [],
        "selected_category": selected,
        "keyword": f"{selected} edit",
    }


async def ensure_cache():
    """Make sure cache has data. Only refresh if empty or stale, never overwrite good data with empty."""
    cache = load_cache()
    has_data = bool(cache.get("reels"))
    is_stale = time.time() - cache.get("timestamp", 0) > CACHE_MAX_AGE

    if has_data and not is_stale:
        return

    if is_stale:
        new_cache = await refresh_cache()
        new_has_data = bool(new_cache.get("reels"))
        if new_has_data:
            return
        log.warning("Refresh returned empty data, keeping old cache")
    else:
        await refresh_cache()
