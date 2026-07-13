from .netflix import NetflixAccountChecker
from .spotify import SpotifyAccountChecker

ACCOUNT_CHECKERS = {
    "netflix": NetflixAccountChecker,
    "spotify": SpotifyAccountChecker,
}
