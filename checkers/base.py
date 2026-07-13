import asyncio
import aiohttp
from abc import ABC, abstractmethod

class BaseChecker(ABC):
    def __init__(self, timeout=30):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.results = {"valid": 0, "invalid": 0, "error": 0, "total": 0}

    @abstractmethod
    async def check_account(self, email: str, password: str) -> bool:
        pass

    @abstractmethod
    async def check_cookie(self, cookie: str) -> bool:
        pass

    @abstractmethod
    def extract_cookies_from_text(self, text: str) -> list:
        pass

    async def check_accounts_batch(self, combos: list) -> dict:
        self.results = {"valid": 0, "invalid": 0, "error": 0, "total": len(combos), "valid_accounts": [], "invalid_accounts": []}
        sem = asyncio.Semaphore(10)
        async def check_one(combo):
            async with sem:
                try:
                    if ":" in combo:
                        email, password = combo.split(":", 1)
                        result = await self.check_account(email.strip(), password.strip())
                        return (combo, result)
                except:
                    return (combo, None)
                return (combo, None)
        tasks = [check_one(c) for c in combos]
        results = await asyncio.gather(*tasks)
        for combo, result in results:
            if result is True:
                self.results["valid"] += 1
                self.results["valid_accounts"].append(combo)
            elif result is False:
                self.results["invalid"] += 1
            else:
                self.results["error"] += 1
        return self.results

    async def check_cookies_batch(self, cookies: list) -> dict:
        self.results = {"valid": 0, "invalid": 0, "error": 0, "total": len(cookies), "valid_cookies": [], "invalid_cookies": []}
        sem = asyncio.Semaphore(10)
        async def check_one(cookie):
            async with sem:
                try:
                    result = await self.check_cookie(cookie)
                    return (cookie, result)
                except:
                    return (cookie, None)
        tasks = [check_one(c) for c in cookies]
        results = await asyncio.gather(*tasks)
        for cookie, result in results:
            if result is True:
                self.results["valid"] += 1
                self.results["valid_cookies"].append(cookie[:50] + "..." if len(cookie) > 50 else cookie)
            elif result is False:
                self.results["invalid"] += 1
            else:
                self.results["error"] += 1
        return self.results
