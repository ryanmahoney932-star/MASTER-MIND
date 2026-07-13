import re, aiohttp
from ..base import BaseChecker

class RobloxCookieChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Roblox"

    async def check_account(self, email: str, password: str) -> bool:
        return False

    async def check_cookie(self, cookie: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                c = cookie if cookie.startswith(".ROBLOSECURITY=") else f".ROBLOSECURITY={cookie}"
                headers = {"Cookie": c, "User-Agent": "Mozilla/5.0"}
                async with session.get("https://www.roblox.com/my/account", headers=headers, allow_redirects=False) as resp:
                    text = await resp.text()
                    return resp.status == 200 and "Birthday" in text
        except:
            return False

    def extract_cookies_from_text(self, text: str) -> list:
        found = []
        matches = re.findall(r'\.ROBLOSECURITY=([^;\s]+)', text)
        for m in matches:
            found.append(f".ROBLOSECURITY={m}")
        return list(set(found))
import re, aiohttp
from ..base import BaseChecker

class RobloxCookieChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Roblox"

    COOKIE_PATTERNS = [
        r'\.ROBLOSECURITY=([^;\s]+)',
    ]

    async def check_account(self, email: str, password: str) -> bool:
        return False

    async def check_cookie(self, cookie: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "Cookie": cookie if cookie.startswith(".ROBLOSECURITY=") else f".ROBLOSECURITY={cookie}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with session.get(
                    "https://www.roblox.com/my/account",
                    headers=headers,
                    allow_redirects=False
                ) as resp:
                    text = await resp.text()
                    return resp.status == 200 and ("Birthday" in text or "UserId" in text)
        except:
            return False

    def extract_cookies_from_text(self, text: str) -> list:
        found_cookies = []
        for pattern in self.COOKIE_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                cookie_str = f".ROBLOSECURITY={match}"
                if cookie_str not in found_cookies:
                    found_cookies.append(cookie_str)
        return list(set(found_cookies))
