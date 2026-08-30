"""Pydantic response models for the search API."""

from pydantic import BaseModel


class BookSummary(BaseModel):
    book_id: int
    title: str
    authors: list[str]
    isbn13: str | None = None
    average_rating: float | None = None
    cover_image_url: str | None = None


class BookDetail(BookSummary):
    isbn10: str | None = None
    description: str | None = None
    publisher: str | None = None
    publish_year: int | None = None
    num_pages: int | None = None
    language: str | None = None
    ratings_count: int | None = None
    price: float | None = None
    genres: list[str]


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[BookSummary]


class GenreCount(BaseModel):
    name: str
    book_count: int


class RecommendationItem(BookSummary):
    """A ranked recommendation: a book plus why it surfaced. ``score`` is
    method-specific and only meaningful for ordering within one response.
    """

    score: float
    reason: str


class RecommendResponse(BaseModel):
    query: str
    method: str
    count: int
    results: list[RecommendationItem]


class MethodInfo(BaseModel):
    """One row of ``GET /recommend/methods`` - what a method is and whether it
    can serve a request right now.
    """

    name: str
    tier: str
    description: str
    available: bool
    unavailable_reason: str = ""


class HealthResponse(BaseModel):
    status: str
    book_count: int
