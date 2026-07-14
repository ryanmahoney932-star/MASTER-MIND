import os, re, time, asyncio, aiohttp, tempfile, zipfile, tarfile
from urllib.parse import urlparse
from config import DOWNLOAD_TIMEOUT, CHUNK_SIZE, PROGRESS_INTERVAL

class PasswordRequired(Exception):
    pass

class ThrottledProgress:
    def __init__(self, callback, min_interval=PROGRESS_INTERVAL):
        self.callback = callback
        self.min_interval = min_interval
        self.last_update = 0
        self.latest = None

    async def __call__(self, *args):
        self.latest = args
        now = time.time()
        if now - self.last_update >= self.min_interval:
            self.last_update = now
            await self.callback(*args)

    async def flush(self):
        if self.latest is not None:
            await self.callback(*self.latest)
            self.latest = None

def format_size(size_bytes):
    if size_bytes >= 1073741824:
        return f"{size_bytes / 1073741824:.2f} GB"
    elif size_bytes >= 1048576:
        return f"{size_bytes / 1048576:.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} B"

def format_speed(bytes_per_sec):
    if bytes_per_sec >= 1048576:
        return f"{bytes_per_sec / 1048576:.1f} MB/s"
    elif bytes_per_sec >= 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec:.0f} B/s"

def extract_urls(text: str) -> list[str]:
    return re.findall(r'https?://\S+', text)

def filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    if not name:
        name = "downloaded_file"
    name = name.split('?')[0]
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name if name else "downloaded_file"

def is_archive(filename: str) -> bool:
    return filename.endswith(('.zip', '.tar.gz', '.tgz', '.tar.bz2', '.bz2', '.tar'))

def extract_archive(archive_path: str, password: str = None) -> list[str]:
    extracted_files = []
    extract_dir = tempfile.mkdtemp()
    try:
        if archive_path.endswith('.zip'):
            try:
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    # Check for encryption
                    for info in zf.infolist():
                        if info.flag_bits & 0x1:  # encrypted
                            if password is None:
                                raise PasswordRequired("Password needed.")
                            zf.setpassword(password.encode())
                            break
                    zf.extractall(extract_dir)
            except zipfile.BadZipFile:
                return []
            except RuntimeError as e:
                if "password" in str(e).lower() or "encrypted" in str(e).lower():
                    raise PasswordRequired("Password needed.")
                return []
            except Exception as e:
                if "encrypted" in str(e).lower() or "password" in str(e).lower():
                    raise PasswordRequired("Password needed.")
                return []
        elif archive_path.endswith(('.tar.gz', '.tgz', '.tar.bz2', '.bz2', '.tar')):
            try:
                with tarfile.open(archive_path, 'r:*') as tf:
                    tf.extractall(extract_dir)
            except tarfile.TarError:
                return []
        else:
            return []

        for root, dirs, files in os.walk(extract_dir):
            for f in files:
                full_path = os.path.join(root, f)
                try:
                    # Try multiple encodings to read as text
                    text_read = False
                    for encoding in ['utf-8', 'latin-1', 'utf-16', 'cp1252']:
                        try:
                            with open(full_path, 'r', encoding=encoding) as test:
                                test.readline()
                            text_read = True
                            break
                        except:
                            continue
                    if text_read:
                        extracted_files.append(full_path)
                except:
                    pass
        return extracted_files
    except PasswordRequired:
        raise
    except:
        return []

async def download_file(url: str, dest_path: str, progress_callback=None, resume=False):
    start = time.time()
    server_response_time = 0
    existing_size = 0
    headers = {}
    if resume and os.path.exists(dest_path):
        existing_size = os.path.getsize(dest_path)
        if existing_size > 0:
            headers['Range'] = f'bytes={existing_size}-'
    try:
        timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT, connect=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status not in (200, 206):
                    return False, 0, 0, 0, False
                server_response_time = time.time() - start
                total_size = int(resp.headers.get('Content-Length', 0))
                if resp.status == 206:
                    total_size += existing_size
                downloaded = existing_size
                mode = 'ab' if existing_size > 0 else 'wb'
                with open(dest_path, mode) as f:
                    async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            await progress_callback(downloaded, total_size if total_size > 0 else downloaded)
                duration = time.time() - start
                return True, downloaded, duration, server_response_time, (existing_size > 0)
    except Exception as e:
        print(f"Download error: {e}")
        return False, 0, 0, 0, False

async def stream_search(url: str, search_text: str, use_regex: bool = False) -> tuple:
    results = []
    total_lines = 0
    start = time.time()
    try:
        timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT, connect=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return [], 0, 0
                buffer = ""
                async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                    text_chunk = chunk.decode('utf-8', errors='ignore')
                    buffer += text_chunk
                    lines = buffer.split('\n')
                    buffer = lines.pop()
                    for line in lines:
                        total_lines += 1
                        if _match_line(line, search_text, use_regex):
                            results.append(line.rstrip())
                if buffer:
                    total_lines += 1
                    if _match_line(buffer, search_text, use_regex):
                        results.append(buffer.rstrip())
        duration = time.time() - start
        return results, total_lines, duration
    except Exception as e:
        print(f"Stream search error: {e}")
        return [], 0, 0

def _match_line(line: str, search_text: str, use_regex: bool) -> bool:
    if use_regex:
        try:
            return bool(re.search(search_text, line))
        except re.error:
            return search_text.lower() in line.lower()
    return search_text.lower() in line.lower()

async def download_forwarded_file(chat_id, document, dest_path, context, session, fname, progress_msg_id):
    start = time.time()
    file_size = document.file_size or 0
    try:
        tg_file = await context.bot.get_file(document.file_id)
        telegram_file_url = tg_file.file_path
        if file_size > 50 * 1048576:
            async def progress_cb(current, total):
                if total:
                    pct = int(current / total * 100)
                    bar_len = 10
                    filled = int(pct / 100 * bar_len)
                    elapsed = time.time() - start
                    speed = current / elapsed if elapsed > 0 else 0
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=progress_msg_id,
                        text=f"📥 Forwarded: {fname}\n▕{'█' * filled}{'░' * (bar_len - filled)}▏ {pct}%\n⚡ {format_speed(speed)}  |  {format_size(current)} / {format_size(total)}")
            throttled = ThrottledProgress(progress_cb)
            success, size, duration, server_response, resumed = await download_file(telegram_file_url, dest_path, progress_callback=throttled, resume=True)
            await throttled.flush()
            if success:
                return True, size, duration
            raise Exception("Custom download failed")
        else:
            async def progress_cb(current, total):
                if total:
                    pct = int(current / total * 100)
                    bar_len = 10
                    filled = int(pct / 100 * bar_len)
                    elapsed = time.time() - start
                    speed = current / elapsed if elapsed > 0 else 0
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=progress_msg_id,
                        text=f"📥 Forwarded: {fname}\n▕{'█' * filled}{'░' * (bar_len - filled)}▏ {pct}%\n⚡ {format_speed(speed)}  |  {format_size(current)} / {format_size(total)}")
            throttled = ThrottledProgress(progress_cb) if file_size > 0 else None
            await tg_file.download_to_drive(dest_path, read_timeout=7200, write_timeout=7200, progress=throttled)
            if throttled:
                await throttled.flush()
            duration = time.time() - start
            size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
            return True, size, duration
    except Exception as e:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=progress_msg_id, text=f"📥 Retrying via direct URL...")
            tg_file = await context.bot.get_file(document.file_id)
            telegram_file_url = tg_file.file_path
            async def fallback_progress(current, total):
                if total:
                    pct = int(current / total * 100)
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=progress_msg_id, text=f"📥 Forwarded: {fname}\n{pct}% - {format_size(current)}")
            throttled = ThrottledProgress(fallback_progress, min_interval=3.0)
            success, size, duration, server_response, resumed = await download_file(telegram_file_url, dest_path, progress_callback=throttled, resume=True)
            await throttled.flush()
            if success:
                return True, size, duration
            raise Exception("Fallback download failed")
        except Exception as e2:
            raise e2
