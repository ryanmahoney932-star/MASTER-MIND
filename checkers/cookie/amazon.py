import re, aiohttp
from ..base import BaseChecker

class NetflixCookieChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Netflix"

    async def check_account(self, email: str, password: str) -> bool:
        return False

    async def check_cookie(self, cookie: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}
                async with session.get("https://www.netflix.com/YourAccount", headers=headers, allow_redirects=False) as resp:
                    text = await resp.text()
                    return resp.status == 200 and ("memberSince" in text or "accountDetails" in text)
        except:
            return False

    def extract_cookies_from_text(self, text: str) -> list:
        found = []
        pattern = r'(NetflixId=[^;]+;\s*SecureNetflixId=[^;]+[^\n]*)'
        matches = re.findall(pattern, text)
        found.extend(matches)
        return list(set(found))
