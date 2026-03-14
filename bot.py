"""
Job Hunter Telegram Bot
------------------------
Commands:
  /scrape          — run a fresh scrape right now
  /jobs            — list new jobs above threshold
  /tailor <id>     — tailor resume for a job id
  /tailor <url>    — tailor resume for any job URL
  /funded          — show recently funded companies with careers pages
  /applied <id>    — mark job as applied
  /skip <id>       — mark job as skipped

The bot also runs a daily scrape automatically at 08:00 local time.
"""

import asyncio
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
import scraper
import tailor as tailor_mod

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_line(job: dict, idx: int | None = None) -> str:
    prefix = f"{idx}. " if idx is not None else "• "
    score_bar = "🟢" if job["score"] >= 75 else "🟡" if job["score"] >= 55 else "🔴"
    return (
        f"{prefix}{score_bar} *{job['score']}* — {job['company']}\n"
        f"   _{job['title'][:70]}_\n"
        f"   {job.get('reason', '')}\n"
        f"   [link]({job['url']})\n"
        f"   `id: {job['id']}`"
    )


async def send(app: Application, text: str):
    await app.bot.send_message(
        chat_id=CHAT_ID, text=text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ── Scheduled scrape ──────────────────────────────────────────────────────────

async def scheduled_scrape(app: Application):
    logger.info("Running scheduled scrape...")
    await send(app, "🔍 Running morning job scrape...")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scraper.run_scrape)

    if not result.get("surfaced"):
        await send(app, f"✅ Scrape done — {result['total']} jobs checked, none above threshold {result['threshold']}.")
        return

    lines = [f"📋 *Job Digest* — {result['total']} scraped, {len(result['surfaced'])} matched\n"]
    for i, job in enumerate(result["surfaced"][:10], 1):
        lines.append(_job_line(job, i))

    lines.append("\nReply `/tailor <id>` to tailor your resume for a job.")
    await send(app, "\n\n".join(lines))


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Scraping... this takes ~30s")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scraper.run_scrape)

    if not result.get("surfaced"):
        await update.message.reply_text(
            f"✅ Done — {result['total']} jobs checked, none above threshold {result['threshold']}."
        )
        return

    lines = [f"📋 *Job Digest* — {result['total']} scraped, {len(result['surfaced'])} matched\n"]
    for i, job in enumerate(result["surfaced"][:10], 1):
        lines.append(_job_line(job, i))
    lines.append("\nUse `/tailor <id>` to tailor your resume.")

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = db.list_jobs(status="new", limit=15)
    if not jobs:
        await update.message.reply_text("No new jobs in the queue. Run /scrape first.")
        return

    lines = [f"📬 *{len(jobs)} jobs in queue*\n"]
    for i, job in enumerate(jobs, 1):
        lines.append(_job_line(job, i))

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_tailor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/tailor <job_id>` or `/tailor <url>`")
        return

    arg = args[0]
    await update.message.reply_text("✍️ Tailoring resume... (~20s)")

    loop = asyncio.get_event_loop()

    if arg.startswith("http"):
        result = await loop.run_in_executor(None, lambda: tailor_mod.tailor(url=arg))
    else:
        result = await loop.run_in_executor(None, lambda: tailor_mod.tailor(job_id=arg))

    if "error" in result:
        await update.message.reply_text(f"❌ {result['error']}")
        return

    folder = os.path.basename(result["out_dir"])
    changed = result.get("changed_files", [])
    changed_str = "\n".join(f"  • `{f}`" for f in changed) if changed else "  _(no changes needed)_"
    await update.message.reply_text(
        f"✅ Resume tailored for *{result['company']}*\n\n"
        f"📁 Folder: `data/resumes/{folder}/`\n\n"
        f"Changed files:\n{changed_str}\n\n"
        f"Copy the folder contents into your Overleaf project to apply.",
        parse_mode="Markdown",
    )

    # Mark job as tailored in DB
    if not arg.startswith("http") and result.get("company"):
        db.set_status(arg, "tailored")


async def cmd_funded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    companies = db.list_funded(limit=15)
    if not companies:
        await update.message.reply_text("No funded companies yet. Run /scrape first.")
        return

    lines = [f"💰 *Recently funded companies with open roles*\n"]
    for c in companies:
        careers = f"[careers]({c['careers_url']})" if c.get("careers_url") else "no careers page found"
        lines.append(f"• *{c['company']}* — {c['amount']} ({c['round_type']})\n  {careers}")

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_applied(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/applied <job_id>`")
        return
    db.set_status(context.args[0], "applied")
    await update.message.reply_text("✅ Marked as applied.")


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/skip <job_id>`")
        return
    db.set_status(context.args[0], "skipped")
    await update.message.reply_text("👍 Skipped.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Job Hunter Bot*\n\n"
        "/scrape — run a fresh scrape now\n"
        "/jobs — list jobs in queue\n"
        "/tailor `<id or url>` — tailor resume for a job\n"
        "/funded — show recently funded companies\n"
        "/applied `<id>` — mark job as applied\n"
        "/skip `<id>` — skip a job\n",
        parse_mode="Markdown",
    )


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silently ignore messages from anyone other than your own chat."""
    if update.effective_chat.id != CHAT_ID:
        logger.warning(f"Ignoring message from unknown chat {update.effective_chat.id}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    db.init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Security: only respond to your own chat
    own_chat = filters.Chat(chat_id=CHAT_ID)

    app.add_handler(CommandHandler("start", cmd_help, filters=own_chat))
    app.add_handler(CommandHandler("help", cmd_help, filters=own_chat))
    app.add_handler(CommandHandler("scrape", cmd_scrape, filters=own_chat))
    app.add_handler(CommandHandler("jobs", cmd_jobs, filters=own_chat))
    app.add_handler(CommandHandler("tailor", cmd_tailor, filters=own_chat))
    app.add_handler(CommandHandler("funded", cmd_funded, filters=own_chat))
    app.add_handler(CommandHandler("applied", cmd_applied, filters=own_chat))
    app.add_handler(CommandHandler("skip", cmd_skip, filters=own_chat))
    app.add_handler(MessageHandler(~own_chat, guard))

    # Daily scrape at 08:00
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_scrape,
        trigger="cron",
        hour=8, minute=0,
        kwargs={"app": app},
        id="daily_scrape",
    )
    scheduler.start()
    logger.info("Scheduler started — daily scrape at 08:00")

    logger.info("Bot polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
