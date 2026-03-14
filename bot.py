"""
Job Hunter Telegram Bot — full featured version
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
import scraper as scraper_mod
import tailor as tailor_mod

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
IST = timezone(timedelta(hours=5, minutes=30))

# ConversationHandler states
JOURNAL_TEXT, CONFIG_FIELD, CONFIG_VALUE = range(3)

PAGE_SIZE = 10  # jobs per page in /alljobs


def now_ist() -> str:
    return datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")


# ── Keyboards ─────────────────────────────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Scrape now", callback_data="scrape"),
         InlineKeyboardButton("📋 My queue", callback_data="jobs")],
        [InlineKeyboardButton("📊 All results", callback_data="alljobs_0"),
         InlineKeyboardButton("💰 Funded cos", callback_data="funded")],
        [InlineKeyboardButton("⚙️ Config", callback_data="show_config"),
         InlineKeyboardButton("📓 Journal", callback_data="journal_menu")],
        [InlineKeyboardButton("💾 Backup DB", callback_data="backup")],
    ])


def job_action_keyboard(job_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Tailor resume", callback_data=f"tailor_{job_id}"),
         InlineKeyboardButton("✅ Applied", callback_data=f"applied_{job_id}")],
        [InlineKeyboardButton("⏭ Skip", callback_data=f"skip_{job_id}"),
         InlineKeyboardButton("🔙 Back", callback_data="jobs")],
    ])


def pagination_keyboard(page: int, total_pages: int, prefix: str):
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("◀ Prev", callback_data=f"{prefix}_{page - 1}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton("Next ▶", callback_data=f"{prefix}_{page + 1}"))
    return InlineKeyboardMarkup([row, [InlineKeyboardButton("🏠 Menu", callback_data="menu")]])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_emoji(score: int) -> str:
    if score >= 75: return "🟢"
    if score >= 55: return "🟡"
    return "🔴"


def _job_block(job: dict, show_status=False) -> str:
    em = _score_emoji(job.get("score", 0))
    wt = job.get("work_type", "") or ""
    wt_tag = f" `{wt}`" if wt and wt != "unspecified" else ""
    status_tag = f" _{job.get('status','')}_" if show_status else ""
    src = job.get("source", "")
    return (
        f"{em} *{job.get('score', 0)}* — {job.get('company', '?')}{wt_tag}{status_tag}\n"
        f"  _{job.get('title', '')[:70]}_\n"
        f"  {job.get('reason', '')}\n"
        f"  [{src}]({job.get('url', '')}) · `{job['id']}`"
    )


async def _send(app, text, reply_markup=None):
    await app.bot.send_message(
        chat_id=CHAT_ID, text=text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


async def _edit(query, text, reply_markup=None):
    await query.edit_message_text(
        text=text, parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


# ── /start and menu ───────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = db.count_jobs()
    new = db.count_jobs("new")
    await update.message.reply_text(
        f"👋 *Job Hunter Bot*\n_{now_ist()}_\n\n"
        f"DB: *{total}* total jobs, *{new}* unreviewed\n\nWhat do you want to do?",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    total = db.count_jobs()
    new = db.count_jobs("new")
    await _edit(query,
        f"👋 *Job Hunter Bot*\n_{now_ist()}_\n\n"
        f"DB: *{total}* total jobs, *{new}* unreviewed\n\nWhat do you want to do?",
        main_menu_keyboard(),
    )


# ── Scrape ────────────────────────────────────────────────────────────────────

async def _do_scrape(app):
    await _send(app, "⏳ Scraping job boards... (~30s)")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scraper_mod.run_scrape)

    total = result["total"]
    surfaced = result["surfaced"]
    threshold = result["threshold"]
    filtered_count = result.get("filtered", total)

    if not surfaced:
        await _send(app,
            f"✅ *Scrape done* — _{now_ist()}_\n\n"
            f"Scraped: {total} · Passed filters: {filtered_count} · Above {threshold}: 0",
            main_menu_keyboard(),
        )
        return

    header = (
        f"📋 *Job Digest* — _{now_ist()}_\n"
        f"Scraped: {total} · Filtered: {filtered_count} · Matched: {len(surfaced)}\n\n"
    )
    blocks = [_job_block(j) for j in surfaced[:10]]
    msg = header + "\n\n".join(blocks)
    if len(surfaced) > 10:
        msg += f"\n\n_...and {len(surfaced) - 10} more. Use 📊 All results to see everything._"
    await _send(app, msg, main_menu_keyboard())


async def cmd_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _do_scrape(context.application)


async def cb_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _do_scrape(context.application)


async def scheduled_scrape(app):
    logger.info("Running scheduled scrape (IST 08:00)")
    await _do_scrape(app)


# ── Job queue ─────────────────────────────────────────────────────────────────

async def _show_jobs(app_or_query, is_callback=False):
    jobs = db.list_jobs(status="new", limit=15)
    if not jobs:
        text = "📭 No new jobs in queue.\n\nRun a scrape first."
        if is_callback:
            await _edit(app_or_query, text, main_menu_keyboard())
        else:
            await _send(app_or_query, text, main_menu_keyboard())
        return

    blocks = [_job_block(j, i + 1) for i, j in enumerate(jobs)]

    def _job_block(job, idx):
        em = _score_emoji(job.get("score", 0))
        wt = job.get("work_type", "") or ""
        wt_tag = f" `{wt}`" if wt and wt != "unspecified" else ""
        return (
            f"{idx}. {em} *{job.get('score',0)}* — {job.get('company','?')}{wt_tag}\n"
            f"   _{job.get('title','')[:65]}_\n"
            f"   {job.get('reason','')}\n"
            f"   `{job['id']}`"
        )

    blocks = [_job_block(j, i + 1) for i, j in enumerate(jobs)]
    text = f"📬 *{len(jobs)} jobs in queue*\n\nUse `/tailor <id>` or tap a job:\n\n" + "\n\n".join(blocks)

    # Quick-action buttons for first 5 jobs
    kbd_rows = []
    for job in jobs[:5]:
        kbd_rows.append([
            InlineKeyboardButton(
                f"✍️ {job['company'][:20]}",
                callback_data=f"tailor_{job['id']}"
            ),
            InlineKeyboardButton("⏭", callback_data=f"skip_{job['id']}"),
        ])
    kbd_rows.append([InlineKeyboardButton("🏠 Menu", callback_data="menu")])
    kbd = InlineKeyboardMarkup(kbd_rows)

    if is_callback:
        await _edit(app_or_query, text, kbd)
    else:
        await _send(app_or_query, text, kbd)


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_jobs(context.application)


async def cb_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await _show_jobs(update.callback_query, is_callback=True)


# ── All jobs (paginated) ──────────────────────────────────────────────────────

async def _show_all_jobs(query_or_app, page: int, is_callback=False):
    all_jobs = db.list_all_jobs(limit=1000)
    total = len(all_jobs)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = all_jobs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines = [f"📊 *All scraped jobs* (page {page+1}/{total_pages}, {total} total)\n"]
    for job in chunk:
        em = _score_emoji(job.get("score", 0))
        src = (job.get("source") or "")[:10]
        wt = (job.get("work_type") or "")
        status = job.get("status", "")
        lines.append(
            f"{em} *{job.get('score',0):3d}* `{src:<12}` "
            f"{'🌐' if wt=='remote' else '🏢' if wt=='onsite' else '  '} "
            f"{job.get('company','?')[:18]} — _{job.get('title','')[:40]}_\n"
            f"   {job.get('reason','')[:80]}\n"
            f"   `{job['id']}` [{status}]"
        )

    text = "\n\n".join(lines)
    kbd = pagination_keyboard(page, total_pages, "alljobs")

    if is_callback:
        await _edit(query_or_app, text, kbd)
    else:
        await _send(query_or_app, text, kbd)


async def cmd_alljobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_all_jobs(context.application, 0)


async def cb_alljobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[1])
    await _show_all_jobs(query, page, is_callback=True)


# ── Tailor ────────────────────────────────────────────────────────────────────

async def _do_tailor(app, arg: str):
    await _send(app, "✍️ Tailoring resume... (~20s)")
    loop = asyncio.get_event_loop()

    if arg.startswith("http"):
        result = await loop.run_in_executor(None, lambda: tailor_mod.tailor(url=arg))
    else:
        result = await loop.run_in_executor(None, lambda: tailor_mod.tailor(job_id=arg))

    if "error" in result:
        await _send(app, f"❌ {result['error']}", main_menu_keyboard())
        return

    zip_path = result["zip_path"]
    changed = result.get("changed_files", [])
    changed_str = "\n".join(f"  • `{f}`" for f in changed) or "  _(none)_"

    caption = (
        f"✅ Tailored for *{result['company']}*\n\n"
        f"Changed:\n{changed_str}\n\n"
        f"Upload the zip directly to Overleaf → New Project → Upload Project."
    )

    with open(zip_path, "rb") as f:
        await app.bot.send_document(
            chat_id=CHAT_ID,
            document=InputFile(f, filename=os.path.basename(zip_path)),
            caption=caption,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    if not arg.startswith("http"):
        db.set_status(arg, "tailored")


async def cmd_tailor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/tailor <job_id or url>`")
        return
    await _do_tailor(context.application, context.args[0])


async def cb_tailor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    job_id = query.data.replace("tailor_", "", 1)
    await _do_tailor(context.application, job_id)


# ── Applied / Skip ────────────────────────────────────────────────────────────

async def cb_applied(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    job_id = query.data.replace("applied_", "", 1)
    db.set_status(job_id, "applied")
    await _edit(query, f"✅ Marked as applied: `{job_id}`", main_menu_keyboard())


async def cb_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    job_id = query.data.replace("skip_", "", 1)
    db.set_status(job_id, "skipped")
    await _edit(query, f"⏭ Skipped: `{job_id}`", main_menu_keyboard())


async def cmd_applied(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        db.set_status(context.args[0], "applied")
        await update.message.reply_text("✅ Marked as applied.", reply_markup=main_menu_keyboard())


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        db.set_status(context.args[0], "skipped")
        await update.message.reply_text("⏭ Skipped.", reply_markup=main_menu_keyboard())


# ── Funded companies ──────────────────────────────────────────────────────────

async def cb_funded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    companies = db.list_funded(15)
    if not companies:
        await _edit(query, "No funded companies yet. Run /scrape first.", main_menu_keyboard())
        return
    lines = [f"💰 *Recently funded — {now_ist()}*\n"]
    for c in companies:
        careers = f"[careers]({c['careers_url']})" if c.get("careers_url") else "no page found"
        lines.append(f"• *{c['company']}* — {c['amount']} ({c['round_type']})\n  {careers}")
    await _edit(query, "\n\n".join(lines),
                InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))


# ── Config ────────────────────────────────────────────────────────────────────

async def cb_show_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cfg = db.get_config()
    text = (
        f"⚙️ *Search config*\n\n"
        f"Keywords: `{', '.join(cfg.get('keywords', []))}`\n"
        f"Work type: `{', '.join(cfg.get('work_type', []))}`\n"
        f"YoE: `{cfg.get('min_yoe', 0)}–{cfg.get('max_yoe', 10)}`\n"
        f"Exclude locations: `{', '.join(cfg.get('exclude_locations', []))}`\n"
        f"Score threshold: `{cfg.get('score_threshold', 60)}`\n\n"
        f"Edit with `/config <field> <value>`\n"
        f"Fields: `keywords`, `work_type`, `min_yoe`, `max_yoe`, `exclude_locations`, `score_threshold`\n"
        f"Comma-separated for lists. Example:\n"
        f"`/config work_type remote,hybrid`\n"
        f"`/config keywords web3,solidity,backend,go`\n"
        f"`/config score_threshold 55`"
    )
    await _edit(query, text, InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        cfg = db.get_config()
        await update.message.reply_text(
            f"⚙️ Current config:\n```\n{json.dumps(cfg, indent=2)}\n```\n\n"
            f"Usage: `/config <field> <value>`",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    field, raw_value = args[0], " ".join(args[1:])
    cfg = db.get_config()
    list_fields = {"keywords", "work_type", "exclude_locations"}
    int_fields = {"min_yoe", "max_yoe", "score_threshold"}

    if field in list_fields:
        cfg[field] = [v.strip() for v in raw_value.split(",") if v.strip()]
    elif field in int_fields:
        try:
            cfg[field] = int(raw_value)
        except ValueError:
            await update.message.reply_text(f"❌ `{field}` must be a number.")
            return
    else:
        await update.message.reply_text(f"❌ Unknown field `{field}`.")
        return

    db.set_config(cfg)
    await update.message.reply_text(
        f"✅ Updated `{field}` → `{cfg[field]}`",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


# ── Journal ───────────────────────────────────────────────────────────────────

async def cb_journal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    entries = db.get_journal_entries(5)
    recent = "\n".join(
        f"• _{e['created_at'][:16]}_: {e['entry'][:80]}" for e in entries
    ) or "_No entries yet._"
    text = (
        f"📓 *Daily Journal*\n\n"
        f"Recent entries:\n{recent}\n\n"
        f"Send `/journal <what you did today>` to log an entry.\n"
        f"Send `/resumediff` to get AI-suggested resume updates based on your journal."
    )
    await _edit(query, text, InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]))


async def cmd_journal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "Usage: `/journal <what you worked on today>`\n\n"
            "Example: `/journal Fixed RabbitMQ retry logic in the pipeline, reviewed PR for Go monitoring service`"
        )
        return
    now = datetime.now(IST).isoformat()
    db.add_journal_entry(text, now)
    await update.message.reply_text(
        f"📓 Logged _{now[:16]}_\n\n_{text}_\n\nUse `/resumediff` anytime to get resume update suggestions.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def cmd_resumediff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entries = db.get_journal_entries(30)
    if not entries:
        await update.message.reply_text("No journal entries yet. Use `/journal` first.")
        return

    journal_text = "\n".join(
        f"[{e['created_at'][:10]}] {e['entry']}" for e in reversed(entries)
    )

    await update.message.reply_text("🧠 Analysing journal entries...")

    import llm
    loop = asyncio.get_event_loop()

    def _get_diff():
        return llm.chat(f"""You are a resume advisor for a software engineer.

Below are their recent work journal entries:

{journal_text}

Their current resume covers:
- RapidNode: AI data pipeline, Go monitoring, LangChain agent
- Clamp: ERC4337, gas optimisation, React Native
- Syntax Studios: Web3 Chrome wallet, Coinbase swap widget

Based on the journal entries, suggest specific resume updates:
1. New bullet points to add (with exact LaTeX \\item text)
2. Existing bullets to strengthen with new details
3. New skills to add to the skills section

Be specific and concise. Format as a clear numbered list.""",
            max_tokens=800, temperature=0.4,
        )

    result = await loop.run_in_executor(None, _get_diff)
    await update.message.reply_text(
        f"📝 *Resume update suggestions*\n\n{result}",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


# ── Fallback / guard ──────────────────────────────────────────────────────────


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _do_backup(context.application)


async def cb_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Preparing backup...")
    await _do_backup(context.application)


async def _do_backup(app):
    import io
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M")
    db_path = os.environ.get("DB_PATH", "/app/data/jobs.db")
    if not os.path.exists(db_path):
        await _send(app, "No DB file found yet.")
        return
    with open(db_path, "rb") as f:
        await app.bot.send_document(
            chat_id=CHAT_ID,
            document=InputFile(f, filename=f"jobs_backup_{ts}.db"),
            caption=f"💾 DB backup — {ts} IST\n\nTo restore: replace jobs.db in ./data/ and restart.",
            reply_markup=main_menu_keyboard(),
        )

async def cb_noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        logger.warning(f"Ignoring chat {update.effective_chat.id}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    db.init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    own = filters.Chat(chat_id=CHAT_ID)

    # Commands
    app.add_handler(CommandHandler("start",      cmd_start,      filters=own))
    app.add_handler(CommandHandler("help",       cmd_start,      filters=own))
    app.add_handler(CommandHandler("scrape",     cmd_scrape,     filters=own))
    app.add_handler(CommandHandler("jobs",       cmd_jobs,       filters=own))
    app.add_handler(CommandHandler("alljobs",    cmd_alljobs,    filters=own))
    app.add_handler(CommandHandler("tailor",     cmd_tailor,     filters=own))
    app.add_handler(CommandHandler("applied",    cmd_applied,    filters=own))
    app.add_handler(CommandHandler("skip",       cmd_skip,       filters=own))
    app.add_handler(CommandHandler("config",     cmd_config,     filters=own))
    app.add_handler(CommandHandler("journal",    cmd_journal,    filters=own))
    app.add_handler(CommandHandler("resumediff", cmd_resumediff, filters=own))
    app.add_handler(CommandHandler("backup",     cmd_backup,     filters=own))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(cb_menu,        pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(cb_scrape,      pattern="^scrape$"))
    app.add_handler(CallbackQueryHandler(cb_jobs,        pattern="^jobs$"))
    app.add_handler(CallbackQueryHandler(cb_alljobs,     pattern=r"^alljobs_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_tailor,      pattern=r"^tailor_"))
    app.add_handler(CallbackQueryHandler(cb_applied,     pattern=r"^applied_"))
    app.add_handler(CallbackQueryHandler(cb_skip,        pattern=r"^skip_"))
    app.add_handler(CallbackQueryHandler(cb_funded,      pattern="^funded$"))
    app.add_handler(CallbackQueryHandler(cb_show_config, pattern="^show_config$"))
    app.add_handler(CallbackQueryHandler(cb_journal_menu,pattern="^journal_menu$"))
    app.add_handler(CallbackQueryHandler(cb_backup,      pattern="^backup$"))
    app.add_handler(CallbackQueryHandler(cb_noop,        pattern="^noop$"))

    # Security
    app.add_handler(MessageHandler(~own, guard))

    # Daily scrape at 08:00 IST
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        scheduled_scrape, trigger="cron",
        hour=8, minute=0,
        kwargs={"app": app},
    )
    scheduler.start()
    logger.info("Bot started. Daily scrape at 08:00 IST.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
