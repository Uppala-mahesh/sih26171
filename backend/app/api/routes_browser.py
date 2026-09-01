from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.browser.browser_manager import BrowserManager
from app.browser.screenshot import ScreenshotManager
from app.dependencies import get_browser_manager, get_screenshot_manager
from app.models.schemas import BrowserStartRequest, BrowserStartResponse, BrowserStopResponse

router = APIRouter(prefix="/api/browser", tags=["browser"])


@router.post("/start", response_model=BrowserStartResponse)
async def start_browser(
    payload: BrowserStartRequest,
    manager: BrowserManager = Depends(get_browser_manager),
) -> BrowserStartResponse:
    await manager.start(str(payload.url))
    return BrowserStartResponse(status="started", url=str(payload.url))


@router.post("/stop", response_model=BrowserStopResponse)
async def stop_browser(
    manager: BrowserManager = Depends(get_browser_manager),
) -> BrowserStopResponse:
    if not manager.is_running:
        return BrowserStopResponse(status="already_stopped")

    await manager.stop()
    return BrowserStopResponse(status="stopped")


@router.get("/screenshot")
async def get_screenshot(
    screenshot_manager: ScreenshotManager = Depends(get_screenshot_manager),
) -> Response:
    try:
        image_bytes = await screenshot_manager.capture()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return Response(content=image_bytes, media_type="image/png")
