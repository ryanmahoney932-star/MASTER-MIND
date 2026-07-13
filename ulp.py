"""
Universal Login Panel - Pure checker logic
No Telegram dependencies
"""
from checkers.netflix import NetflixChecker
from checkers.spotify import SpotifyChecker

# Registry of all checkers
CHECKERS = {
    "netflix": NetflixChecker,
    "spotify": SpotifyChecker,
    # Add more: "hulu": HuluChecker, "disney": DisneyChecker, etc.
}

class ULP:
    def __init__(self):
        self.checkers = {}
        self.stats = {"total_checked": 0, "valid": 0, "invalid": 0, "error": 0}

    def get_checker(self, site: str):
        site = site.lower()
        if site not in CHECKERS:
            return None
        if site not in self.checkers:
            self.checkers[site] = CHECKERS[site]()
        return self.checkers[site]

    async def check(self, combos: list, mode: str = "account", site: str = None) -> dict:
        """Check combos. If site is None, tries all checkers."""
        if site:
            checker = self.get_checker(site)
            if not checker:
                return {"error": f"No checker for {site}"}
            results = await checker.check_batch(combos, mode)
            self._update_stats(results)
            return {site: results}
        else:
            all_results = {}
            for site_name in CHECKERS:
                checker = CHECKERS[site_name]()
                results = await checker.check_batch(combos, mode)
                if results["valid"] > 0 or results["invalid"] > 0:
                    all_results[site_name] = results
                    self._update_stats(results)
            return all_results

    def _update_stats(self, results: dict):
        for key in self.stats:
            self.stats[key] += results.get(key, 0)

    def get_stats(self) -> dict:
        return self.stats

    def list_checkers(self) -> list:
        return list(CHECKERS.keys())

# Global instance
"""
Universal Login Panel - Pure checker logic
No Telegram dependencies
"""
from checkers.netflix import NetflixChecker
from checkers.spotify import SpotifyChecker

# Registry of all checkers
CHECKERS = {
    "netflix": NetflixChecker,
    "spotify": SpotifyChecker,
    # Add more: "hulu": HuluChecker, "disney": DisneyChecker, etc.
}

class ULP:
    def __init__(self):
        self.checkers = {}
        self.stats = {"total_checked": 0, "valid": 0, "invalid": 0, "error": 0}

    def get_checker(self, site: str):
        site = site.lower()
        if site not in CHECKERS:
            return None
        if site not in self.checkers:
            self.checkers[site] = CHECKERS[site]()
        return self.checkers[site]

    async def check(self, combos: list, mode: str = "account", site: str = None) -> dict:
        """Check combos. If site is None, tries all checkers."""
        if site:
            checker = self.get_checker(site)
            if not checker:
                return {"error": f"No checker for {site}"}
            results = await checker.check_batch(combos, mode)
            self._update_stats(results)
            return {site: results}
        else:
            all_results = {}
            for site_name in CHECKERS:
                checker = CHECKERS[site_name]()
                results = await checker.check_batch(combos, mode)
                if results["valid"] > 0 or results["invalid"] > 0:
                    all_results[site_name] = results
                    self._update_stats(results)
            return all_results

    def _update_stats(self, results: dict):
        for key in self.stats:
            self.stats[key] += results.get(key, 0)

    def get_stats(self) -> dict:
        return self.stats

    def list_checkers(self) -> list:
        return list(CHECKERS.keys())

# Global instance
ulp = ULP()
