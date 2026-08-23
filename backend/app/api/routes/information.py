from fastapi import APIRouter, Depends, HTTPException, Query

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
    if ((page - 1) * size) + 1 > 1000:
        raise HTTPException(
            status_code=422,
            detail="NAVER 뉴스 검색의 start 값은 1000 이하여야 합니다.",
        )
    return service.get_korean_news(page, size)
