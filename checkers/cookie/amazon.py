import re, aiohttp
from ..base import BaseChecker

class AmazonCookieChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Amazon"

    async def check_account(self, email: str, password: str) -> bool:
        return False

    async def check_cookie(self, cookie: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}
                async with session.get("https://www.amazon.com/gp/yourstore/home", headers=headers, allow_redirects=False) as resp:
                    text = await resp.text()
                    return resp.status == 200 and "Your Account" in text
        except:
            return False

    def extract_cookies_from_text(self, text: str) -> list:
        found = []
        patterns = [r'session-id=([^;\s]+)', r'ubid-main=([^;\s]+)']
        for p in patterns:
            matches = re.findall(p, text)
            for m in matches:
                found.append(f"{p.split('=')[0]}={m}")
        return list(set(found))
import re, aiohttp
from ..base import BaseChecker

class AmazonCookieChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Amazon"

    COOKIE_PATTERNS = [
        r'session-id=([^;\s]+)',
        r'session-id-time=([^;\s]+)',
        r'ubid-main=([^;\s]+)',
        r'at-main=([^;\s]+)',
    ]

    async def check_account(self, email: str, password: str) -> bool:
        return False

    async def check_cookie(self, cookie: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "Cookie": cookie,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with session.get(
                    "https://www.amazon.com/gp/yourstore/home",
                    headers=headers,
                    allow_redirects=False
                ) as resp:
                    text = await resp.text()
                    return resp.status == 200 and ("Your Account" in text or "nav-link-accountList" in text)
        except:
            return False

    def extract_cookies_from_text(self, text: str) -> list:
        found_cookies = []
        for pattern in self.COOKIE_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                cookie_str = f"{pattern.split('=')[0]}={match}"
                if cookie_str not in found_cookies:
                    found_cookies.append(cookie_str)
        return list(set(found_cookies))
