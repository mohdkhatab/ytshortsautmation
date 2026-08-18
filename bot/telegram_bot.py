import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from logger import log
from agent.orchestrator import AnimeUploadAgent
from db.database import get_task, get_user_tasks
import config

agent = AnimeUploadAgent()


def is_allowed(user_id: int) -> bool:
    if not config.ALLOWED_USERS:
        return True
    return user_id in config.ALLOWED_USERS


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start New Task", callback_data="new_task")],
        [InlineKeyboardButton("📊 My Recent Tasks", callback_data="my_tasks")],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
    ])


def task_running_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Task", callback_data=f"cancel_{task_id}")],
        [InlineKeyboardButton("📊 Status", callback_data=f"status_{task_id}")],
    ])


def back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")],
    ])


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return
    await update.message.reply_text(
        "🎬 **Anime Upload Agent**\n\n"
        "Main automatically anime editing videos dhundhta hoon,\n"
        "Instagram se trending reels analyze karta hoon,\n"
        "AI se title/description generate karta hoon,\n"
        "aur YouTube Shorts pe upload kar deta hoon!\n\n"
        "**Flow:** Instagram Search → yt-dlp Premium Download → AI Generate → YouTube Upload\n\n"
        "👇 Neeche button dabao:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /status <task_id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid task ID.")
        return
    task = get_task(task_id)
    if not task:
        await update.message.reply_text("Task not found.")
        return
    emoji = {"pending":"⏳","searching":"🔍","analyzing":"📊","generating":"🤖","downloading":"⬇️","uploading":"📤","polling":"🔄","completed":"✅","failed":"❌"}.get(task.get("status",""), "❓")
    await update.message.reply_text(
        f"**Task #{task_id}**\n\n"
        f"Status: {emoji} {task.get('status','').upper()}\n"
        f"Category: {task.get('category','N/A')}\n"
        f"Title: {task.get('title','N/A')}\n"
        f"Source: {task.get('source_url','N/A')}\n"
        f"Upload: {task.get('upload_url','N/A')}\n"
        f"Error: {task.get('error','None')}\n",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    tasks = get_user_tasks(update.effective_user.id, limit=5)
    if not tasks:
        await update.message.reply_text("Koi tasks nahi hai. /start se naya task banao.")
        return
    text = "📋 **Recent Tasks:**\n\n"
    emoji_map = {"pending":"⏳","searching":"📸","analyzing":"📊","generating":"🤖","downloading":"⬇️","uploading":"📤","polling":"🔄","completed":"✅","failed":"❌"}
    for t in tasks:
        e = emoji_map.get(t.get("status",""), "❓")
        text += f"#{t['id']} {e} {t.get('status','').upper()}"
        if t.get("title"):
            text += f" | {t['title'][:40]}"
        text += "\n"
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode="Markdown")


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /cancel <task_id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid task ID.")
        return
    if agent.cancel_task(task_id):
        await update.message.reply_text(f"❌ Task #{task_id} cancelled.")
    else:
        await update.message.reply_text(f"Task #{task_id} already finished ya exist nahi karta.")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_allowed(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return

    data = query.data

    if data == "back_to_menu":
        await query.edit_message_text(
            "🎬 **Anime Upload Agent**\n\n👇 Neeche button dabao:",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown",
        )
        return

    if data == "help":
        await query.edit_message_text(
            "❓ **How it works:**\n\n"
            "1. **Start New Task** dabao\n"
            "2. Agent Instagram pe trending anime reels dhundega\n"
            "3. YouTube + AnimeThemes se backup lega\n"
            "4. yt-dlp se premium quality mein download karega\n"
            "5. AI se title, description, tags banega\n"
            "6. YouTube Shorts API pe upload karega\n"
            "7. Tumhe notification aa jayega!\n\n"
            "**Commands:**\n"
            "/start - Main menu\n"
            "/status <id> - Task status\n"
            "/tasks - Recent tasks\n"
            "/cancel <id> - Cancel task\n\n"
            "**Priority:** Instagram > YouTube > AnimeThemes",
            reply_markup=back_button(),
            parse_mode="Markdown",
        )
        return

    if data == "new_task":
        await query.edit_message_text(
            "🚀 **Naya Task Start!**\n\n"
            "📸 Instagram pe anime content search ho raha hai...\n"
            "⏰ Ye 3-7 minute lega.\n\n"
            "Tumhe har step pe update milega!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏳ Processing...", callback_data="noop")],
            ]),
            parse_mode="Markdown",
        )

        chat_id = query.message.chat.id
        task_id = agent.start_task(chat_id)

        async def status_updater(message):
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=query.message.message_id,
                    text=f"🔄 **Task #{task_id} - Running...**\n\nLatest update will appear here.",
                    reply_markup=task_running_keyboard(task_id),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        agent.set_status_callback(task_id, status_updater)

        async def poll_status():
            for _ in range(180):
                await asyncio.sleep(5)
                task = get_task(task_id)
                if not task:
                    break
                s = task.get("status", "")
                if s in ("completed", "failed"):
                    break
                emoji = {"pending":"⏳","searching":"📸","analyzing":"📊","generating":"🤖","downloading":"⬇️","uploading":"📤","polling":"🔄"}.get(s, "❓")
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=query.message.message_id,
                        text=f"🔄 **Task #{task_id}** {emoji} {s.upper()}\n\n"
                             f"📂 Category: {task.get('category', 'Auto')}\n"
                             f"📌 Title: {task.get('title', 'Generating...')}\n"
                             f"🔗 Source: {task.get('source_url', 'Searching...')}\n",
                        reply_markup=task_running_keyboard(task_id),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

        asyncio.create_task(poll_status())
        await query.answer()
        return

    if data == "my_tasks":
        tasks = get_user_tasks(query.from_user.id, limit=5)
        if not tasks:
            await query.edit_message_text(
                "📋 Koi tasks nahi hai abhi.\nPehla task start karo!",
                reply_markup=back_button(),
            )
            await query.answer()
            return
        text = "📋 **Recent Tasks:**\n\n"
        emoji_map = {"pending":"⏳","searching":"📸","analyzing":"📊","generating":"🤖","downloading":"⬇️","uploading":"📤","polling":"🔄","completed":"✅","failed":"❌"}
        for t in tasks:
            e = emoji_map.get(t.get("status",""), "❓")
            text += f"#{t['id']} {e} {t.get('status','').upper()}"
            if t.get("title"):
                text += f" | {t['title'][:40]}"
            text += "\n"
        await query.edit_message_text(text, reply_markup=back_button(), parse_mode="Markdown")
        await query.answer()
        return

    if data.startswith("cancel_"):
        task_id = int(data.split("_")[1])
        if agent.cancel_task(task_id):
            await query.answer("Task cancelled!", show_alert=True)
            try:
                await query.edit_message_text(
                    f"❌ **Task #{task_id} Cancelled**\n\nNaya task: /start",
                    reply_markup=back_button(),
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        else:
            await query.answer("Task already finished.", show_alert=True)
        return

    if data.startswith("status_"):
        task_id = int(data.split("_")[1])
        task = get_task(task_id)
        if task:
            await query.answer(f"Status: {task.get('status','').upper()}", show_alert=True)
        else:
            await query.answer("Task not found.", show_alert=True)
        return

    if data == "noop":
        await query.answer()
        return

    await query.answer()


def run_bot():
    log.info("Starting Anime Upload Telegram Bot (python-telegram-bot)...")
    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("tasks", tasks_cmd))
    application.add_handler(CommandHandler("cancel", cancel_cmd))
    application.add_handler(CallbackQueryHandler(callback_handler))

    log.info("Bot is running! Send /start in Telegram.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
