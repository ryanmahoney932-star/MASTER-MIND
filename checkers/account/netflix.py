import aiohttp
from ..base import BaseChecker

class NetflixAccountChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Netflix"

    async def check_account(self, email: str, password: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
                data = {"email": email, "password": password, "rememberMe": "true"}
                async with session.post("https://www.netflix.com/api/login", json=data, headers=headers) as resp:
                    result = await resp.json()
                    return result.get("status") == "success"
        except:
            return False

    async def check_cookie(self, cookie: str) -> bool:
        return False

    def extract_cookies_from_text(self, text: str) -> list:
import aiohttp
from ..base import BaseChecker

class NetflixAccountChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Netflix"

    async def check_account(self, email: str, password: str) -> bool:
        """Check Netflix account via login."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Netflix login API
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Content-Type": "application/json"
                }
                data = {
                    "email": email,
                    "password": password,
                    "rememberMe": "true"
                }
                async with session.post(
                    "https://www.netflix.com/api/login",
                    json=data,
                    headers=headers
                ) as resp:
                    result = await resp.json()
                    return result.get("status") == "success"
        except:
            return False

    async def check_cookie(self, cookie: str) -> bool:
        return False

    def extract_cookies_from_text(self, text: str) -> list:
        return []
