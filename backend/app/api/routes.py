from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse
from uuid import uuid4

import tls_requests
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.core.proxy_manager import ProxyManager
from app.schemas.models import (
    ProductDetail,
    ProxyConfigPayload,
    ProxyErrorEvent,
    ProxyRecord,
    ProxyStatus,
    ProxyTogglePayload,
    SearchResponse,
    SourceName,
)
from app.services.marketplace_service import MarketplaceService

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

_proxy_manager = ProxyManager()
_marketplace_service = MarketplaceService(_proxy_manager)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Hosts we are willing to proxy images from.
# Browsers can't load some of these directly (Referer / hotlink policy on Ozon CDN),
# so we re-serve them through the backend with proper headers.
_ALLOWED_IMAGE_HOST_SUFFIXES = (
    "ozone.ru",
    "ozon.ru",
    "wbbasket.ru",
    "wb.ru",
    "wildberries.ru",
    "kaspi.kz",
)

_IMAGE_PROXY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@router.get("/image-proxy")
async def image_proxy(url: str = Query(..., min_length=8)) -> Response:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="bad scheme")

    host = (parsed.netloc or "").lower()
    if not host or not any(
        host == suffix or host.endswith("." + suffix)
        for suffix in _ALLOWED_IMAGE_HOST_SUFFIXES
    ):
        raise HTTPException(status_code=400, detail="host not allowed")

    referer = f"{parsed.scheme}://{parsed.netloc}/"
    headers = {
        "User-Agent": _IMAGE_PROXY_UA,
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.9",
    }

    try:
        resp = await asyncio.to_thread(
            tls_requests.get,
            url,
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("image_proxy fetch failed url=%s err=%s", url, exc)
        raise HTTPException(status_code=502, detail="upstream fetch failed") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail="upstream error")

    content_type = resp.headers.get("content-type") or "image/jpeg"
    return Response(
        content=resp.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/search", response_model=SearchResponse)
async def search(query: str = Query(..., min_length=2)) -> SearchResponse:
    request_id = str(uuid4())
    started_at = time.perf_counter()
    response = await _marketplace_service.search(query, request_id=request_id)
    logger.info(
        "api_search_done request_id=%s latency_ms=%s query_len=%s",
        request_id,
        int((time.perf_counter() - started_at) * 1000),
        len(query),
    )
    return response


@router.get("/product-details", response_model=ProductDetail)
async def product_details(source: SourceName, product_url: str) -> ProductDetail:
    request_id = str(uuid4())
    started_at = time.perf_counter()
    try:
        detail = await _marketplace_service.get_product_details(
            source=source,
            product_url=product_url,
            request_id=request_id,
        )
        logger.info(
            "api_detail_done request_id=%s source=%s latency_ms=%s",
            request_id,
            source.value,
            int((time.perf_counter() - started_at) * 1000),
        )
        return detail
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "api_detail_failed request_id=%s source=%s latency_ms=%s err=%s",
            request_id,
            source.value,
            int((time.perf_counter() - started_at) * 1000),
            exc,
        )
        raise HTTPException(status_code=502, detail=f"Failed to fetch product details: {exc}") from exc


@router.post("/proxies/file", response_model=list[ProxyRecord])
async def upload_proxies_file(file: UploadFile = File(...)) -> list[ProxyRecord]:
    payload = await file.read()
    text = payload.decode("utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines()]
    return _proxy_manager.load_from_lines(lines)


@router.post("/proxies/text", response_model=list[ProxyRecord])
async def upload_proxies_text(payload: ProxyConfigPayload) -> list[ProxyRecord]:
    lines = [line.strip() for line in payload.proxies_text.splitlines()]
    return _proxy_manager.load_from_lines(lines)


@router.post("/proxies/toggle", response_model=ProxyStatus)
async def toggle_proxies(payload: ProxyTogglePayload) -> ProxyStatus:
    _proxy_manager.set_enabled(payload.enabled)
    return _proxy_manager.status()


@router.get("/proxies/status", response_model=ProxyStatus)
async def proxy_status() -> ProxyStatus:
    return _proxy_manager.status()


@router.get("/proxies/errors", response_model=list[ProxyErrorEvent])
async def proxy_errors(limit: int = 50) -> list[ProxyErrorEvent]:
    return _proxy_manager.recent_errors(limit=limit)
