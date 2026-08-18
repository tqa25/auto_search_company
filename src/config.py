"""
Centralized configuration module for the Vietnamese company contact-data extraction pipeline.

All configuration values are read from environment variables with hard-coded defaults.
Import `default_config` for a ready-to-use instance, or instantiate `Config()` directly.
"""

import json
import os
from dotenv import load_dotenv

load_dotenv(override=True)


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


def _validate_api_key(key_name: str, value: str | None, min_length: int = 10) -> str | None:
    """Validate API key format. Returns stripped key or None if invalid/missing."""
    if not value or len(value.strip()) < min_length:
        return None
    return value.strip()


class Config:
    """
    Configuration container for the extraction pipeline.

    All attributes are populated from environment variables on instantiation,
    with sensible hard-coded defaults when variables are absent.
    """

    def __init__(self) -> None:
        # --- API Keys (validated) ---
        self.FIRECRAWL_API_KEY: str | None = _validate_api_key(
            "FIRECRAWL_API_KEY", os.getenv("FIRECRAWL_API_KEY")
        )
        self.GEMINI_API_KEY: str | None = _validate_api_key(
            "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")
        )
        # --- Search group ---
        self.SEARCH_LIMIT: int = _parse_int(
            os.getenv("SEARCH_LIMIT"), default=100
        )
        self.EARLY_STOP_COUNT: int = _parse_int(
            os.getenv("EARLY_STOP_COUNT"), default=10
        )
        self.EARLY_STOP_SCORE: int = _parse_int(
            os.getenv("EARLY_STOP_SCORE"), default=35
        )
        self.FB_FALLBACK_THRESHOLD: int = _parse_int(
            os.getenv("FB_FALLBACK_THRESHOLD"), default=3
        )
        self.INFER_MAX_SCRAPE: int = _parse_int(
            os.getenv("INFER_MAX_SCRAPE"), default=2
        )
        
        # --- Vietnamese name inference ---
        self.VN_LEGAL_DOMAINS: list = _parse_str_list(
            os.getenv("VN_LEGAL_DOMAINS"),
            default=["masothue.com", "thuvienphapluat.vn", "yellowpages.vn", "hosocongty.vn", "dangkykinhdoanh.gov.vn"],
        )

        # --- Scoring group (JSON dicts) ---
        self.DOMAIN_SCORES: dict = _parse_json_dict(
            os.getenv("DOMAIN_SCORES"),
            default={"official": 15, "legal": 30, "job": 30, "social": -100, "name_match": 15},
        )
        self.KEYWORD_SCORES: dict = _parse_json_dict(
            os.getenv("KEYWORD_SCORES"),
            default={"contact": 10, "admin": 10, "recruitment": 5},
        )
        
        self.TLD_SCORES: dict = _parse_json_dict(
            os.getenv("TLD_SCORES"),
            default={
                ".vn": 5, ".com.vn": 5, ".com": 5, ".net": 5, ".org": 5, ".org.vn": 5,
                ".info": 2, ".biz": 2,
                ".top": 2, ".xyz": 2, ".club": 2, ".tk": 2, ".ml": 2, ".ga": 2
            }
        )
        self.KNOWN_DOMAINS: dict = _parse_json_dict(
            os.getenv("KNOWN_DOMAINS"),
            default={
                "thuvienphapluat.vn": ("thuvienphapluat", "legal"),
                "hosocongty.vn": ("hosocongty", "legal"),
                "vietnamworks.com": ("vietnamworks", "job"),
                "topcv.vn": ("topcv", "job"),
                "vietcareer.vn": ("vietcareer", "job"),
                "jobsgo.vn": ("jobsgo", "job"),
                "facebook.com": ("facebook", "social"),
                "linkedin.com": ("linkedin", "social"),
                "yellowpages.vn": ("yellowpages", "official"),
                "masothue.com": ("masothue", "legal"),
            },
        )

        # --- Scrape group ---
        self.TOP_N: int = _parse_int(
            os.getenv("TOP_N"), default=10
        )
        self.FIRECRAWL_BATCH_SCRAPE_ENABLED: bool = _parse_bool(
            os.getenv("FIRECRAWL_BATCH_SCRAPE_ENABLED"), default=False
        )
        self.FIRECRAWL_MAX_CONCURRENCY: int = _parse_int(
            os.getenv("FIRECRAWL_MAX_CONCURRENCY"), default=10
        )
        self.FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS: float = _parse_float(
            os.getenv("FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS"), default=2.0
        )
        self.FIRECRAWL_BATCH_TIMEOUT_SECONDS: float = _parse_float(
            os.getenv("FIRECRAWL_BATCH_TIMEOUT_SECONDS"), default=300.0
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
        self._max_retries: int = _parse_int(
            os.getenv("MAX_RETRIES"), default=3
        )
        # MAX_ATTEMPTS = 1 initial + retries (new semantic)
        # e.g., MAX_ATTEMPTS=3 means 1 initial + 2 retries = 3 total calls
        self.MAX_ATTEMPTS: int = _parse_int(
            os.getenv("MAX_ATTEMPTS"), default=3
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

        # --- Gemini Quick Search (Bước 1) ---
        self.GEMINI_QUICK_ENABLED: bool = _parse_bool(
            os.getenv("GEMINI_QUICK_ENABLED"), default=True
        )
        self.AI_GROUNDING_MODEL: str = os.getenv(
            "AI_GROUNDING_MODEL", os.getenv("GEMINI_QUICK_MODEL", "gemini-1.5-flash")
        )
        self.GEMINI_QUICK_CONFIDENCE_THRESHOLD: float = _parse_float(
            os.getenv("GEMINI_QUICK_CONFIDENCE_THRESHOLD"), default=0.7
        )
        self.GEMINI_DAILY_LIMIT: int = _parse_int(
            os.getenv("GEMINI_DAILY_LIMIT"), default=1450
        )
        self.GEMINI_DAILY_WARN_PERCENT: float = _parse_float(
            os.getenv("GEMINI_DAILY_WARN_PERCENT"), default=0.9
        )



        # --- AI Extractor ---
        self.AI_EXTRACTOR_MODEL: str = os.getenv(
            "AI_EXTRACTOR_MODEL", "gemini-2.0-flash"
        )

        # --- Source toggles ---
        self.SCRAPE_LINKEDIN_ENABLED: bool = _parse_bool(
            os.getenv("SCRAPE_LINKEDIN_ENABLED"), default=False
        )
        self.BUSINESS_STATUS_GATE_ENABLED: bool = _parse_bool(
            os.getenv("BUSINESS_STATUS_GATE_ENABLED"), default=True
        )
        self.REPORT_CUTOFF_TIME: str = os.getenv("REPORT_CUTOFF_TIME", "17:00")
        
        # --- Dynamic Overrides from pipeline_config.json ---
        self._load_pipeline_config()

    def _load_pipeline_config(self):
        """Override config values from pipeline_config.json if it exists."""
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pipeline_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Iterate through expected keys and override if present
                keys_to_override = [
                    "SEARCH_LIMIT", "EARLY_STOP_COUNT", "EARLY_STOP_SCORE", "INFER_MAX_SCRAPE",
                    "DOMAIN_SCORES", "KEYWORD_SCORES", "TOP_N", 
                    "FIRECRAWL_BATCH_SCRAPE_ENABLED", "FIRECRAWL_MAX_CONCURRENCY",
                    "FIRECRAWL_BATCH_POLL_INTERVAL_SECONDS", "FIRECRAWL_BATCH_TIMEOUT_SECONDS",
                    "ENABLE_QUERY_DEDUP", "ENABLE_URL_DEDUP", "ENABLE_GLOBAL_CACHE", "CACHE_TTL_DAYS",
                    "DELAY_SECONDS", "MAX_RETRIES", "BATCH_SIZE", "MIN_CONFIDENCE_THRESHOLD",
                    "GEMINI_QUICK_ENABLED", "SCRAPE_LINKEDIN_ENABLED",
                    "BUSINESS_STATUS_GATE_ENABLED", "REPORT_CUTOFF_TIME",
                    "MIN_SCRAPE_SCORE", "KNOWN_DOMAINS"
                ]
                
                for k in keys_to_override:
                    if k in data:
                        setattr(self, k, data[k])
                        
                # Note: BLACKLISTED_DOMAINS and SKIP_DOMAINS are used in filter_module directly
                # We can also store them here for completeness
                if "BLACKLISTED_DOMAINS" in data:
                    self.BLACKLISTED_DOMAINS = data["BLACKLISTED_DOMAINS"]
                if "SKIP_DOMAINS" in data:
                    self.SKIP_DOMAINS = data["SKIP_DOMAINS"]
                    
            except Exception as e:
                print(f"Warning: Failed to load pipeline_config.json: {e}")


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
            f"ENABLE_QUERY_DEDUP={self.ENABLE_QUERY_DEDUP!r}, "
            f"ENABLE_URL_DEDUP={self.ENABLE_URL_DEDUP!r}, "
            f"ENABLE_GLOBAL_CACHE={self.ENABLE_GLOBAL_CACHE!r}, "
            f"CACHE_TTL_DAYS={self.CACHE_TTL_DAYS!r}, "
            f"FORCE_REFRESH={self.FORCE_REFRESH!r}, "
            f"DELAY_SECONDS={self.DELAY_SECONDS!r}, "
            f"MAX_RETRIES={self.MAX_RETRIES!r}, "
            f"MAX_ATTEMPTS={self.MAX_ATTEMPTS!r}, "
            f"EXECUTION_MODE={self.EXECUTION_MODE!r}, "
            f"BATCH_SIZE={self.BATCH_SIZE!r}, "
            f"ABBREVIATION_STOP_WORDS={self.ABBREVIATION_STOP_WORDS!r}, "
            f"MIN_CONFIDENCE_THRESHOLD={self.MIN_CONFIDENCE_THRESHOLD!r}, "
            f"INFER_MAX_SCRAPE={self.INFER_MAX_SCRAPE!r}, "
            f"VN_LEGAL_DOMAINS={self.VN_LEGAL_DOMAINS!r}, "
            f"BUSINESS_STATUS_GATE_ENABLED={self.BUSINESS_STATUS_GATE_ENABLED!r}, "
            f"AI_EXTRACTOR_MODEL={self.AI_EXTRACTOR_MODEL!r}"
            f")"
        )
    
    @property
    def MAX_RETRIES(self) -> int:
        """Deprecated: Use MAX_ATTEMPTS instead. MAX_ATTEMPTS = 1 initial + retries."""
        import warnings
        warnings.warn(
            "MAX_RETRIES is deprecated. Use MAX_ATTEMPTS (1 initial + N retries). "
            "MAX_RETRIES will be removed in a future version.",
            DeprecationWarning,
            stacklevel=2
        )
        return self._max_retries
    
    @MAX_RETRIES.setter
    def MAX_RETRIES(self, value: int):
        self._max_retries = value


# Module-level default instance — import this for convenience.
default_config = Config()
