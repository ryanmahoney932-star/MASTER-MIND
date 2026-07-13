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
