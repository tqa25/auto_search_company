"""
Centralized configuration module for the Vietnamese company contact-data extraction pipeline.

All configuration values are read from environment variables with hard-coded defaults.
Import `default_config` for a ready-to-use instance, or instantiate `Config()` directly.
"""

import json
import os


def _parse_bool(value: str, default: bool) -> bool:
    """Parse a string environment variable as a boolean."""
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes")


def _parse_int(value: str, default: int) -> int:
    """Parse a string environment variable as an integer."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _parse_float(value: str, default: float) -> float:
    """Parse a string environment variable as a float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_json_dict(value: str, default: dict) -> dict:
    """Parse a string environment variable as a JSON dict, falling back to default on error."""
    if value is None:
        return default
    try:
        result = json.loads(value)
        if isinstance(result, dict):
            return result
        return default
    except (ValueError, TypeError):
        return default


def _parse_str_list(value: str, default: list) -> list:
    """Parse a comma-separated string environment variable as a list of stripped strings."""
    if value is None:
        return default
    return [part.strip() for part in value.split(",") if part.strip()]


class Config:
    """
    Configuration container for the extraction pipeline.

    All attributes are populated from environment variables on instantiation,
    with sensible hard-coded defaults when variables are absent.
    """

    def __init__(self) -> None:
        # --- Search group ---
        self.SEARCH_LIMIT: int = _parse_int(
            os.getenv("SEARCH_LIMIT"), default=20
        )
        self.EARLY_STOP_COUNT: int = _parse_int(
            os.getenv("EARLY_STOP_COUNT"), default=5
        )
        self.EARLY_STOP_SCORE: int = _parse_int(
            os.getenv("EARLY_STOP_SCORE"), default=40
        )
        self.FB_FALLBACK_THRESHOLD: int = _parse_int(
            os.getenv("FB_FALLBACK_THRESHOLD"), default=3
        )

        # --- Scoring group (JSON dicts) ---
        self.DOMAIN_SCORES: dict = _parse_json_dict(
            os.getenv("DOMAIN_SCORES"),
            default={"official": 40, "legal": 30, "job": 20, "social": 10, "name_match": 15},
        )
        self.KEYWORD_SCORES: dict = _parse_json_dict(
            os.getenv("KEYWORD_SCORES"),
            default={"contact": 10, "admin": 10, "recruitment": 5},
        )

        # --- Scrape group ---
        self.TOP_N: int = _parse_int(
            os.getenv("TOP_N"), default=10
        )
        self.CONTACT_DISCOVERY_ENABLED: bool = _parse_bool(
            os.getenv("CONTACT_DISCOVERY_ENABLED"), default=True
        )
        self.CONTACT_PATHS: list = _parse_str_list(
            os.getenv("CONTACT_PATHS"),
            default=["/contact", "/lien-he", "/about"],
        )

        # --- Dedup group ---
        self.ENABLE_QUERY_DEDUP: bool = _parse_bool(
            os.getenv("ENABLE_QUERY_DEDUP"), default=True
        )
        self.ENABLE_URL_DEDUP: bool = _parse_bool(
            os.getenv("ENABLE_URL_DEDUP"), default=True
        )
        self.ENABLE_GLOBAL_CACHE: bool = _parse_bool(
            os.getenv("ENABLE_GLOBAL_CACHE"), default=True
        )
        self.CACHE_TTL_DAYS: int = _parse_int(
            os.getenv("CACHE_TTL_DAYS"), default=7
        )
        self.FORCE_REFRESH: bool = _parse_bool(
            os.getenv("FORCE_REFRESH"), default=False
        )

        # --- Rate limit group ---
        self.DELAY_SECONDS: float = _parse_float(
            os.getenv("DELAY_SECONDS"), default=3.0
        )
        self.MAX_RETRIES: int = _parse_int(
            os.getenv("MAX_RETRIES"), default=3
        )

        # --- Pipeline group ---
        self.EXECUTION_MODE: str = os.getenv("EXECUTION_MODE", "auto")
        self.BATCH_SIZE: int = _parse_int(
            os.getenv("BATCH_SIZE"), default=10
        )

        # --- Abbreviation group ---
        self.ABBREVIATION_STOP_WORDS: list = _parse_str_list(
            os.getenv("ABBREVIATION_STOP_WORDS"),
            default=["Co", "Ltd", "Corp", "Inc", "Company", "Joint", "Stock", "Vietnam", "Viet", "JSC", "TNHH", "CP", "Cổ", "Phần"],
        )

        # --- Confidence threshold group ---
        self.MIN_CONFIDENCE_THRESHOLD: float = _parse_float(
            os.getenv("MIN_CONFIDENCE_THRESHOLD"), default=0.3
        )

    def __repr__(self) -> str:
        return (
            f"Config("
            f"SEARCH_LIMIT={self.SEARCH_LIMIT!r}, "
            f"EARLY_STOP_COUNT={self.EARLY_STOP_COUNT!r}, "
            f"EARLY_STOP_SCORE={self.EARLY_STOP_SCORE!r}, "
            f"FB_FALLBACK_THRESHOLD={self.FB_FALLBACK_THRESHOLD!r}, "
            f"DOMAIN_SCORES={self.DOMAIN_SCORES!r}, "
            f"KEYWORD_SCORES={self.KEYWORD_SCORES!r}, "
            f"TOP_N={self.TOP_N!r}, "
            f"CONTACT_DISCOVERY_ENABLED={self.CONTACT_DISCOVERY_ENABLED!r}, "
            f"CONTACT_PATHS={self.CONTACT_PATHS!r}, "
            f"ENABLE_QUERY_DEDUP={self.ENABLE_QUERY_DEDUP!r}, "
            f"ENABLE_URL_DEDUP={self.ENABLE_URL_DEDUP!r}, "
            f"ENABLE_GLOBAL_CACHE={self.ENABLE_GLOBAL_CACHE!r}, "
            f"CACHE_TTL_DAYS={self.CACHE_TTL_DAYS!r}, "
            f"FORCE_REFRESH={self.FORCE_REFRESH!r}, "
            f"DELAY_SECONDS={self.DELAY_SECONDS!r}, "
            f"MAX_RETRIES={self.MAX_RETRIES!r}, "
            f"EXECUTION_MODE={self.EXECUTION_MODE!r}, "
            f"BATCH_SIZE={self.BATCH_SIZE!r}, "
            f"ABBREVIATION_STOP_WORDS={self.ABBREVIATION_STOP_WORDS!r}, "
            f"MIN_CONFIDENCE_THRESHOLD={self.MIN_CONFIDENCE_THRESHOLD!r}"
            f")"
        )


# Module-level default instance — import this for convenience.
default_config = Config()
