from .netflix import NetflixCookieChecker
from .spotify import SpotifyCookieChecker
from .amazon import AmazonCookieChecker
from .roblox import RobloxCookieChecker

COOKIE_CHECKERS = {
    "netflix": NetflixCookieChecker,
    "spotify": SpotifyCookieChecker,
    "amazon": AmazonCookieChecker,
    "roblox": RobloxCookieChecker,
}
