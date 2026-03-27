"""
Public blog routes — listing, single post, category filter.
"""
import re
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.database import get_db
from app.models import BlogPost, BlogCategory, BlogStatus

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _get_user(request):
    """Best-effort current user (returns None if DB not ready)."""
    try:
        from app.routes.auth import get_current_user_from_cookie
        db = next(get_db())
        return get_current_user_from_cookie(request, db), db
    except Exception:
        return None, None


@router.get("/blog")
async def blog_listing(request: Request):
    user, db = _get_user(request)
    if db is None:
        db = next(get_db())

    page = int(request.query_params.get("page", 1))
    per_page = 9
    cat_slug = request.query_params.get("category", "")

    q = db.query(BlogPost).filter(BlogPost.status == BlogStatus.PUBLISHED)
    if cat_slug:
        cat = db.query(BlogCategory).filter(BlogCategory.slug == cat_slug).first()
        if cat:
            q = q.filter(BlogPost.category_id == cat.id)

    total = q.count()
    posts = (
        q.order_by(BlogPost.published_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Eager-load relationships
    for p in posts:
        _ = p.author
        _ = p.category

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    featured = (
        db.query(BlogPost)
        .filter(BlogPost.status == BlogStatus.PUBLISHED, BlogPost.is_featured == True)
        .order_by(BlogPost.published_at.desc())
        .limit(3)
        .all()
    )
    for p in featured:
        _ = p.author
        _ = p.category

    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse("blog.html", {
        "request": request,
        "user": user,
        "posts": posts,
        "featured_posts": featured,
        "categories": categories,
        "current_category": cat_slug,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@router.get("/blog/category/{slug}")
async def blog_by_category(slug: str, request: Request):
    user, db = _get_user(request)
    if db is None:
        db = next(get_db())

    category = db.query(BlogCategory).filter(BlogCategory.slug == slug).first()
    if not category:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/blog")

    page = int(request.query_params.get("page", 1))
    per_page = 9

    q = (
        db.query(BlogPost)
        .filter(BlogPost.status == BlogStatus.PUBLISHED, BlogPost.category_id == category.id)
    )
    total = q.count()
    posts = (
        q.order_by(BlogPost.published_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    for p in posts:
        _ = p.author
        _ = p.category

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse("blog.html", {
        "request": request,
        "user": user,
        "posts": posts,
        "featured_posts": [],
        "categories": categories,
        "current_category": slug,
        "category": category,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@router.get("/blog/{slug}")
async def blog_post(slug: str, request: Request):
    user, db = _get_user(request)
    if db is None:
        db = next(get_db())

    post = db.query(BlogPost).filter(
        BlogPost.slug == slug,
        BlogPost.status == BlogStatus.PUBLISHED,
    ).first()

    if not post:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/blog")

    # Increment views
    post.views = (post.views or 0) + 1
    try:
        db.commit()
    except Exception:
        db.rollback()

    _ = post.author
    _ = post.category

    # Related posts (same category, excluding current)
    related = []
    if post.category_id:
        related = (
            db.query(BlogPost)
            .filter(
                BlogPost.status == BlogStatus.PUBLISHED,
                BlogPost.category_id == post.category_id,
                BlogPost.id != post.id,
            )
            .order_by(BlogPost.published_at.desc())
            .limit(3)
            .all()
        )
        for r in related:
            _ = r.author
            _ = r.category

    return templates.TemplateResponse("blog_post.html", {
        "request": request,
        "user": user,
        "post": post,
        "related_posts": related,
    })
