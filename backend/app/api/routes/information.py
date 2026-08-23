from fastapi import APIRouter, Depends, Query

from app.schemas.api import NewsListResponse
from app.services.news import NewsService

router = APIRouter(prefix="/information", tags=["information"])


def get_news_service() -> NewsService:
    return NewsService()


@router.get("/news/kr", response_model=NewsListResponse)
def korean_news(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    service: NewsService = Depends(get_news_service),
) -> NewsListResponse:
    return service.get_korean_news(page, size)
