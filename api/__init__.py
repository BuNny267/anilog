"""API package exports."""
from api.anilist import (
    ApiError, RateLimitError, NotFoundError,
    search, fetch_metadata, fetch_characters, relations, fetch_schedule,
    current_season, trending, seasonal, popular, top_rated, upcoming, top_movies,
)

__all__ = [
    "ApiError", "RateLimitError", "NotFoundError",
    "search", "fetch_metadata", "fetch_characters", "relations", "fetch_schedule",
    "current_season", "trending", "seasonal", "popular", "top_rated",
    "upcoming", "top_movies",
]