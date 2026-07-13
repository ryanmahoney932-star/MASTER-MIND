import re, aiohttp
from ..base import BaseChecker

class SpotifyCookieChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Spotify"

    async def check_account(self, email: str, password: str) -> bool:
        return False

    async def check_cookie(self, cookie: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}
                async with session.get("https://www.spotify.com/account/overview/", headers=headers, allow_redirects=False) as resp:
                    text = await resp.text()
                    return resp.status == 200 and "premium" in text.lower()
        except:
            return False

    def extract_cookies_from_text(self, text: str) -> list:
        found = []
        pattern = r'(sp_dc=[^;]+;\s*sp_key=[^;]+[^\n]*)'
        matches = re.findall(pattern, text)
        found.extend(matches)
        return list(set(found))
import re, aiohttp
from ..base import BaseChecker

class SpotifyCookieChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Spotify"

    COOKIE_PATTERNS = [
        r'sp_dc=([^;\s]+)',
        r'sp_key=([^;\s]+)',
        r'sp_t=([^;\s]+)',
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
                    "https://www.spotify.com/account/overview/",
                    headers=headers,
                    allow_redirects=False
                ) as resp:
                    text = await resp.text()
                    return resp.status == 200 and "premium" in text.lower()
        except:
            return False

    def extract_cookies_from_text(self, text: str) -> list:
        found_cookies = []
        
        # Complete Spotify cookie pattern
        spotify_pattern = r'(sp_dc=[^;]+;\s*sp_key=[^;]+[^\n]*)'
        matches = re.findall(spotify_pattern, text)
        found_cookies.extend(matches)
        
        for pattern in self.COOKIE_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                cookie_str = f"{pattern.split('=')[0]}={match}"
                if cookie_str not in found_cookies:
                    found_cookies.append(cookie_str)
        
        return list(set(found_cookies))
