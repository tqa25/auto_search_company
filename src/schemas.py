"""
Schema validation for pipeline data structures using dataclasses.
Provides validation helpers to catch data corruption early at module boundaries.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class SearchResult:
    """Schema for search results from Firecrawl."""
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    search_type: str = ""       # "coarse", "fallback_a", etc.
    cache_hit: bool = False
    credits_used: float = 0.0


@dataclass
class ScoredLink:
    """Schema for classified and scored URLs ready for scraping."""
    url: str
    source_type: str = "unknown"
    relevance_score: float = 0.0
    should_scrape: bool = True
    breakdown: dict = field(default_factory=dict)
    reason: str = ""


@dataclass
class ScrapedContent:
    """Schema for scraped page content from Firecrawl."""
    url: str
    markdown: str = ""
    content_length: int = 0
    scrape_status: str = "pending"
    credits_used: float = 0.0
    error_message: Optional[str] = None


@dataclass
class ExtractedContact:
    """Schema for extracted contact information via Gemini."""
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    fax: Optional[str] = None
    representative: Optional[str] = None
    confidence: float = 0.0
    source_type: str = ""
    source_url: str = ""


# Validation helpers

def validate_search_result(data: dict) -> SearchResult:
    """
    Validate and convert dict → SearchResult.

    Args:
        data: Dictionary to validate

    Returns:
        SearchResult instance

    Raises:
        ValueError: If required 'url' field is missing or empty
    """
    if "url" not in data or not data["url"]:
        raise ValueError(f"SearchResult missing required 'url': {data}")
    return SearchResult(**{k: v for k, v in data.items() if k in SearchResult.__dataclass_fields__})


def validate_scored_link(data: dict) -> ScoredLink:
    """
    Validate and convert dict → ScoredLink.

    Args:
        data: Dictionary to validate

    Returns:
        ScoredLink instance

    Raises:
        ValueError: If required 'url' field is missing or empty
    """
    if "url" not in data or not data["url"]:
        raise ValueError(f"ScoredLink missing required 'url': {data}")
    return ScoredLink(**{k: v for k, v in data.items() if k in ScoredLink.__dataclass_fields__})


def validate_scraped_content(data: dict) -> ScrapedContent:
    """
    Validate and convert dict → ScrapedContent.

    Args:
        data: Dictionary to validate

    Returns:
        ScrapedContent instance

    Raises:
        ValueError: If required 'url' field is missing or empty
    """
    if "url" not in data or not data["url"]:
        raise ValueError(f"ScrapedContent missing required 'url': {data}")
    return ScrapedContent(**{k: v for k, v in data.items() if k in ScrapedContent.__dataclass_fields__})


def validate_extracted_contact(data: dict) -> ExtractedContact:
    """
    Validate and convert dict → ExtractedContact.

    Args:
        data: Dictionary to validate

    Returns:
        ExtractedContact instance

    Raises:
        ValueError: If required 'source_url' field is missing or empty
    """
    if "source_url" not in data or not data["source_url"]:
        raise ValueError(f"ExtractedContact missing required 'source_url': {data}")
    return ExtractedContact(**{k: v for k, v in data.items() if k in ExtractedContact.__dataclass_fields__})
