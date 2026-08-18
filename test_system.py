import sys, os, asyncio, json, time
sys.path.insert(0, os.path.dirname(__file__))

from logger import log
import config

PASS = "✅"
FAIL = "❌"
results = []

def test(name, ok, detail=""):
    status = PASS if ok else FAIL
    results.append((name, ok))
    print(f"{status} {name}" + (f" | {detail}" if detail else ""))


async def test_instagram_search():
    print("\n=== TEST 1: Instagram Search (via Google + DuckDuckGo) ===")
    import aiohttp
    from searcher.web_search import search_instagram_via_google, search_instagram_via_duckduckgo

    async with aiohttp.ClientSession() as session:
        r1 = await search_instagram_via_google(session, "naruto edit reel", max_results=5)
        test("Instagram Google search", len(r1) > 0, f"found {len(r1)} reels")
        if r1:
            print(f"   Sample: {r1[0].get('url', 'N/A')}")

        r2 = await search_instagram_via_duckduckgo(session, "anime edit reel", max_results=5)
        test("Instagram DDG search", len(r2) > 0, f"found {len(r2)} reels")
        if r2:
            print(f"   Sample: {r2[0].get('url', 'N/A')}")

        return r1 + r2


async def test_youtube_search():
    print("\n=== TEST 2: YouTube Search ===")
    import aiohttp
    from searcher.web_search import search_youtube_videos

    async with aiohttp.ClientSession() as session:
        r = await search_youtube_videos(session, "naruto amv edit 2024", max_results=5)
        test("YouTube search", len(r) > 0, f"found {len(r)} videos")
        if r:
            print(f"   Sample: {r[0].get('title', '')[:50]} | {r[0].get('url', '')}")
        return r


async def test_ytdlp_download(yt_results):
    print("\n=== TEST 3: yt-dlp Premium Download ===")
    import aiohttp
    from searcher.web_search import download_video_ytdlp

    if not yt_results:
        test("yt-dlp download", False, "no YouTube URL to test")
        return None

    url = yt_results[0]["url"]
    print(f"   Downloading: {url}")
    t0 = time.time()

    async with aiohttp.ClientSession() as session:
        path = await download_video_ytdlp(url, 999, "test_video")

    elapsed = time.time() - t0
    if path:
        size_mb = os.path.getsize(path) / 1024 / 1024
        test("yt-dlp download", True, f"{size_mb:.1f}MB in {elapsed:.1f}s")
        print(f"   File: {path}")
        return path
    else:
        test("yt-dlp download", False, "download failed (bot detection)")
        return None


async def test_ai_generation():
    print("\n=== TEST 4: OpenRouter AI Content Generation ===")
    import aiohttp
    from ai_gen.content_gen import generate_content_with_ai

    fake_results = {
        "selected_category": "Naruto",
        "keyword": "naruto amv edit",
        "instagram": [{"caption": "epic naruto edit 🔥"}],
        "youtube": [{"title": "Naruto Shippuden AMV - God Tier Edit"}],
        "anime_themes": [],
    }

    async with aiohttp.ClientSession() as session:
        t0 = time.time()
        content = await generate_content_with_ai(session, fake_results, 999)
        elapsed = time.time() - t0

    test("AI content generation", bool(content.get("title")), f"{elapsed:.1f}s")
    if content:
        print(f"   Title: {content.get('title', '')}")
        print(f"   Tags: {content.get('tags', [])[:5]}")
        print(f"   Context: {content.get('context', '')[:80]}")
    return content


async def test_upload_api(video_path):
    print("\n=== TEST 5: YouTube Shorts API Upload ===")
    import aiohttp
    from uploader.youtube_upload import upload_via_base64, upload_via_source_url

    async with aiohttp.ClientSession() as session:
        # Test source URL
        print("   Testing source URL workflow...")
        r1 = await upload_via_source_url(
            session, 999,
            "https://www.w3schools.com/html/mov_bbb.mp4",
            "Test Video #Shorts",
            "Test upload.\n\n#Shorts #Anime #Test",
            ["anime", "test", "shorts"],
            ["#Shorts", "#Anime", "#Test"],
            "A test video."
        )
        test("Upload API (source URL)", r1.get("success"), f"jobId={r1.get('job_id', 'N/A')} | {r1.get('error', 'OK')}")

        # Test base64
        if video_path and os.path.exists(video_path):
            size = os.path.getsize(video_path)
            if size <= 30 * 1024 * 1024:
                print(f"   Testing base64 upload ({size/1024/1024:.1f}MB)...")
                r2 = await upload_via_base64(
                    session, 999, video_path,
                    "Test Video #Shorts",
                    "Auto-uploaded.\n\n#Shorts #Anime",
                    ["anime", "edit", "shorts"],
                    ["#Shorts", "#Anime"],
                    "Anime edit video."
                )
                test("Upload API (base64)", r2.get("success"), f"jobId={r2.get('job_id', 'N/A')} | {r2.get('error', 'OK')}")
            else:
                test("Upload API (base64)", False, f"file too large: {size/1024/1024:.1f}MB")
        else:
            test("Upload API (base64)", False, "no video file")

        return r1


async def main():
    print("=" * 60)
    print("   ANIME UPLOAD AGENT - FULL SYSTEM TEST")
    print("=" * 60)

    ig_results = await test_instagram_search()
    yt_results = await test_youtube_search()
    video_path = await test_ytdlp_download(yt_results)
    ai_content = await test_ai_generation()
    upload_result = await test_upload_api(video_path)

    if video_path and os.path.exists(video_path):
        os.remove(video_path)
        print(f"\n🧹 Cleaned up: {video_path}")

    print("\n" + "=" * 60)
    print("   RESULTS SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"\n  {passed}/{total} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
