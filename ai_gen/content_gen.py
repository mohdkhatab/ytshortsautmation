import json
import random
import re
from typing import Optional
import aiohttp

from logger import log
import config


FALLBACK_TITLES = [
    "{anime} Edit That Will Blow Your Mind #Shorts",
    "Insane {anime} Compilation - Ultra HD #Shorts",
    "Best {anime} Moments | {style} Edition #Shorts",
    "{anime} AMV - {mood} Vibes #Shorts",
    "God Tier {anime} Edit #Shorts",
    "TOP {count} {anime} Scenes {style} #Shorts",
    "{anime} {style} Mashup - Pure Fire #Shorts",
]

FALLBACK_DESCRIPTIONS = [
    "Welcome to the ultimate {anime} edit!\n\n"
    "The most epic {anime} moments edited with {style} style.\n\n"
    "Don't forget to LIKE, SUBSCRIBE, and hit the BELL icon!\n"
    "Comment your favorite moment below!\n\n"
    "#anime #animeedit #{hashtag} #amv #Shorts",
]

STYLE_OPTIONS = ["Cinematic", "Dark", "Neon", "Glitch", "Smooth", "4K", "Epic", "Drip", "Phonk"]
MOOD_OPTIONS = ["Dark", "Emotional", "Hype", "Chill", "Epic", "Savage"]


async def generate_content_with_ai(session: aiohttp.ClientSession, search_results: dict, task_id: int) -> dict:
    """Use OpenRouter (nvidia/nemotron-3.5-lightning:free) to generate YouTube Shorts metadata."""
    category = search_results.get("selected_category", "Anime")
    keyword = search_results.get("keyword", "anime edit")

    ig_data = search_results.get("instagram", [])
    yt_data = search_results.get("youtube", [])

    ref_titles = [v.get("title", "") for v in yt_data[:3] if v.get("title")]
    ref_captions = [p.get("caption", "") for p in ig_data[:3] if p.get("caption")]
    ref_captions = [c[:150] for c in ref_captions]

    prompt = f"""You are an expert YouTube Shorts creator specializing in anime content.
Generate optimized metadata for a YouTube Shorts video.

Category: {category}
Search keyword: {keyword}
Reference YouTube titles: {json.dumps(ref_titles)}
Reference Instagram captions: {json.dumps(ref_captions)}

Generate a JSON response with EXACTLY this structure (no markdown, no code blocks, just raw JSON):
{{
  "title": "exact title (max 100 chars, must end with #Shorts, use emojis)",
  "description": "description (max 4500 chars, SEO optimized, include hashtags at end)",
  "hashtags": ["#Shorts", "#Anime", "#AnimeEdit", "up to 5 more relevant hashtags"],
  "tags": ["tag1", "tag2", "up to 15 relevant SEO tags"],
  "context": "1-2 sentence description of what this video contains for AI analysis"
}}

Rules:
- Title MUST be catchy, under 100 chars, end with #Shorts
- Description must be engaging, SEO-friendly, end with hashtags
- Hashtags: start with #Shorts, #Anime, #AnimeEdit then add 5 more relevant ones
- Tags: mix of broad and specific (anime, naruto, amv, edit, viral, etc.)
- Context: describe the video content for the upload API
- ONLY return valid JSON, nothing else"""

    if config.OPENROUTER_API_KEY:
        try:
            log.info(f"[Task {task_id}] Calling OpenRouter ({config.AI_MODEL}) for content generation...")
            ai_result = await _call_openrouter_streaming(session, prompt)
            if ai_result:
                log.info(f"[Task {task_id}] AI generated: title={ai_result.get('title', '')[:60]}...")
                return ai_result
            else:
                log.info(f"[Task {task_id}] Trying non-streaming fallback...")
                ai_result = await _call_openrouter(session, prompt)
                if ai_result:
                    log.info(f"[Task {task_id}] AI generated (non-stream): title={ai_result.get('title', '')[:60]}...")
                    return ai_result
        except Exception as e:
            log.warning(f"[Task {task_id}] OpenRouter failed: {e}, using fallback")

    return _fallback_content(category, keyword)


async def _call_openrouter_streaming(session: aiohttp.ClientSession, prompt: str) -> Optional[dict]:
    """Call OpenRouter with streaming enabled (SSE)."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://anime-upload-agent.local",
        "X-Title": "Anime Upload Agent",
    }
    payload = {
        "model": config.AI_MODEL,
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 1000,
    }

    full_content = ""
    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.warning(f"OpenRouter stream error {resp.status}: {body[:200]}")
                return None

            async for line in resp.content:
                decoded = line.decode("utf-8").strip()
                if not decoded or not decoded.startswith("data:"):
                    continue
                data_str = decoded[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        full_content += token
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        log.warning(f"OpenRouter streaming error: {e}")
        return None

    if not full_content:
        return None

    return _parse_ai_response(full_content)


async def _call_openrouter(session: aiohttp.ClientSession, prompt: str) -> Optional[dict]:
    """Call OpenRouter without streaming (fallback)."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://anime-upload-agent.local",
        "X-Title": "Anime Upload Agent",
    }
    payload = {
        "model": config.AI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 1000,
    }

    async with session.post(url, json=payload, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status == 200:
            data = await resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            return _parse_ai_response(content)
        else:
            body = await resp.text()
            log.warning(f"OpenRouter error {resp.status}: {body[:200]}")
    return None


def _parse_ai_response(content: str) -> Optional[dict]:
    """Parse AI response, handling markdown code blocks and surrounding prose."""
    content = content.strip()
    if content.startswith("```"):
        m = re.match(r"^```[a-zA-Z]*\s*\n", content)
        if m:
            content = content[m.end():]
        elif "\n" in content:
            content = content.split("\n", 1)[1]
        content = re.sub(r"```\s*$", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        log.warning(f"Failed to parse AI JSON: {e}")
        log.debug(f"Raw content: {content[:300]}")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None


def _fallback_content(category: str, keyword: str) -> dict:
    style = random.choice(STYLE_OPTIONS)
    mood = random.choice(MOOD_OPTIONS)
    count = random.choice(["10", "15", "20", "25"])
    hashtag = category.lower().replace(" ", "")

    title = random.choice(FALLBACK_TITLES).format(
        anime=category, style=style, mood=mood, count=count
    )
    description = random.choice(FALLBACK_DESCRIPTIONS).format(
        anime=category, style=style, hashtag=hashtag
    )

    tags = [
        category.lower(), f"{category.lower()} edit", "anime edit", "anime amv",
        "anime fan edit", "anime compilation", "amv edit", "anime edits",
        "viral anime", "anime 2024", "shorts", "reels", "tiktok anime",
        "anime mix", "anime fight",
    ]

    hashtags = ["#Shorts", "#Anime", "#AnimeEdit", f"#{hashtag}", "#AMV", "#Viral"]

    context = f"Anime editing video featuring {category} scenes with {style} style editing."

    return {
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "tags": tags[:15],
        "context": context,
    }


async def generate_content_from_prompt(session: aiohttp.ClientSession, custom_prompt: str,
                                        search_results: dict, task_id: int) -> dict:
    category = search_results.get("selected_category", "Anime")

    if config.OPENROUTER_API_KEY:
        prompt = f"""You are an expert YouTube Shorts creator.
User request: {custom_prompt}
Anime category: {category}

Generate optimized YouTube Shorts metadata as JSON:
{{
  "title": "catchy title (max 100 chars, end with #Shorts)",
  "description": "engaging description (max 4500 chars, SEO optimized, hashtags at end)",
  "hashtags": ["#Shorts", "#Anime", "relevant ones"],
  "tags": ["relevant SEO tags, max 15"],
  "context": "video description for AI analysis"
}}
ONLY return valid JSON."""

        try:
            result = await _call_openrouter_streaming(session, prompt)
            if result:
                return result
            result = await _call_openrouter(session, prompt)
            if result:
                return result
        except Exception:
            pass

    return _fallback_content(category, custom_prompt)
