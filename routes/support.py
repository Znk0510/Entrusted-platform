from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from main import templates
from routes.auth import get_current_user

router = APIRouter()

@router.get("/support", response_class=HTMLResponse)
async def get_support_page(
    request: Request, 
    user: dict | None = Depends(get_current_user)
):
    """
    顯示客服中心頁面
    """
    return templates.TemplateResponse("support.html", {
        "request": request,
        "user": user
    })