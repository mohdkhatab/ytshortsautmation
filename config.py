import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# Telegram
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED_USERS = [int(x.strip()) for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip()]

# YouTube Shorts Upload API
UPLOAD_API_URL = os.getenv("UPLOAD_API_URL", "https://ytshorts-ash-cvi4qyfg.manus.space/api/automation/v1/jobs")
UPLOAD_API_BASE = os.getenv("UPLOAD_API_BASE", "https://ytshorts-ash-cvi4qyfg.manus.space")
UPLOAD_API_KEY = os.getenv("UPLOAD_API_KEY", "")

# OpenRouter AI
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "nvidia/nemotron-3.5-lightning:free")

# Paths
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(BASE_DIR / "downloads")))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "30")) * 1024 * 1024

# DB
DB_PATH = BASE_DIR / "tasks.db"

# Anime categories
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
