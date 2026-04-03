from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/onboarding")
async def onboarding_page(request: Request):
    from app.models import Alert, AlertStatus
    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # If onboarding already complete, go to dashboard
    if user.onboarding_complete:
        return RedirectResponse(url="/dashboard")

    step = int(request.query_params.get("step", "1"))

    unread_alerts = (
        db.query(Alert)
        .filter(Alert.status == AlertStatus.UNREAD)
        .count()
    )

    return templates.TemplateResponse("onboarding.html", {
        "request": request,
        "user": user,
        "step": step,
        "unread_alerts": unread_alerts,
    })


@router.post("/onboarding/step1")
async def onboarding_step1(
    request: Request,
    company_name: str = Form(""),
    company_gstin: str = Form(""),
):
    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    user.company_name = company_name.strip() or None
    user.company_gstin = company_gstin.strip() or None
    db.commit()

    return RedirectResponse(url="/onboarding?step=2", status_code=302)


@router.post("/onboarding/step2")
async def onboarding_step2(request: Request):
    from app.models import Product
    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    product_name = form.get("product_name", "").strip()
    category = form.get("category", "Nutraceutical")
    brand = form.get("brand", "").strip() or None

    if product_name:
        product = Product(
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
async def onboarding_step3(request: Request):
    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    user.onboarding_complete = True
    db.commit()

    return RedirectResponse(url="/dashboard?welcome=1", status_code=302)


@router.post("/onboarding/skip")
async def onboarding_skip(request: Request):
    db = next(get_db())
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    user.onboarding_complete = True
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=302)
