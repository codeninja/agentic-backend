"""Auth strategy modules."""

from ninja_auth.strategies.apikey import ApiKeyStrategy
from ninja_auth.strategies.bearer import BearerStrategy
from ninja_auth.strategies.identity import IdentityStrategy
from ninja_auth.strategies.oauth2 import OAuth2Strategy

__all__ = ["ApiKeyStrategy", "BearerStrategy", "IdentityStrategy", "OAuth2Strategy"]
