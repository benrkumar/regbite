from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product
from app.routes.auth import get_current_user_from_cookie
from app.services.access_control import get_account_id
from app.services.alert_service import count_unread_alerts

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_user(request: Request, db: Session):
    return get_current_user_from_cookie(request, db)


@router.get("/onboarding")
async def onboarding_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if user.onboarding_complete:
        return RedirectResponse(url="/dashboard")

    step = int(request.query_params.get("step", "1"))
    return templates.TemplateResponse("onboarding.html", {
        "request": request,
        "user": user,
        "step": step,
        "unread_alerts": count_unread_alerts(db, user),
    })


@router.post("/onboarding/step1")
async def onboarding_step1(
    request: Request,
    company_name: str = Form(""),
    company_gstin: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    user.company_name = company_name.strip() or None
    user.company_gstin = company_gstin.strip() or None
    db.commit()
    return RedirectResponse(url="/onboarding?step=2", status_code=302)


@router.post("/onboarding/step2")
async def onboarding_step2(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    product_name = form.get("product_name", "").strip()
    category = form.get("category", "Nutraceutical")
    brand = form.get("brand", "").strip() or None

    if product_name:
        product = Product(
            account_id=get_account_id(user),
            user_id=user.id,
            name=product_name,
            category=category,
            brand=brand,
            is_active=True,
        )
        db.add(product)
        db.commit()

    return RedirectResponse(url="/onboarding?step=3", status_code=302)


@router.post("/onboarding/step3")
async def onboarding_step3(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    user.onboarding_complete = True
    db.commit()
    return RedirectResponse(url="/dashboard?welcome=1", status_code=302)


@router.post("/onboarding/skip")
async def onboarding_skip(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    user.onboarding_complete = True
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)
