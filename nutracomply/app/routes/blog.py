"""
Blog routes — public blog listing + post detail, and admin blog management.
"""
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.models import (
    BlogPost, BlogCategory, BlogPostStatus,
    Alert, AlertStatus, User,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_admin(request: Request, db: Session):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None, RedirectResponse(url="/login")
    if not user.is_admin:
        return None, RedirectResponse(url="/dashboard")
    return user, None


def _slugify(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:350]


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC BLOG ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/blog")
async def blog_listing(request: Request, db: Session = Depends(get_db)):
    category_slug = request.query_params.get("category", "")
    tag = request.query_params.get("tag", "")
    page = int(request.query_params.get("page", 1))
    per_page = 12

    q = db.query(BlogPost).filter(BlogPost.status == BlogPostStatus.PUBLISHED)

    if category_slug:
        cat = db.query(BlogCategory).filter(BlogCategory.slug == category_slug).first()
        if cat:
            q = q.filter(BlogPost.category_id == cat.id)

    if tag:
        q = q.filter(BlogPost.tags.ilike(f"%{tag}%"))

    total = q.count()
    posts = (
        q.order_by(BlogPost.published_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Eager load relationships
    for p in posts:
        _ = p.category
        _ = p.author

    featured = (
        db.query(BlogPost)
        .filter(BlogPost.status == BlogPostStatus.PUBLISHED, BlogPost.is_featured == True)
        .order_by(BlogPost.published_at.desc())
        .limit(3)
        .all()
    )
    for p in featured:
        _ = p.category
        _ = p.author

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()

    # Try to get user for nav
    try:
        user = get_current_user_from_cookie(request, db)
    except Exception:
        user = None

    return templates.TemplateResponse("blog_list.html", {
        "request": request,
        "user": user,
        "posts": posts,
        "featured": featured,
        "categories": categories,
        "current_category": category_slug,
        "current_tag": tag,
        "page": page,
        "total": total,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    })


@router.get("/blog/{slug}")
async def blog_post(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter(
        BlogPost.slug == slug,
        BlogPost.status == BlogPostStatus.PUBLISHED,
    ).first()

    if not post:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    # Increment views
    post.views = (post.views or 0) + 1
    db.commit()

    _ = post.category
    _ = post.author

    # Related posts (same category, exclude current)
    related = []
    if post.category_id:
        related = (
            db.query(BlogPost)
            .filter(
                BlogPost.status == BlogPostStatus.PUBLISHED,
                BlogPost.category_id == post.category_id,
                BlogPost.id != post.id,
            )
            .order_by(BlogPost.published_at.desc())
            .limit(3)
            .all()
        )
        for r in related:
            _ = r.category
            _ = r.author

    try:
        user = get_current_user_from_cookie(request, db)
    except Exception:
        user = None

    return templates.TemplateResponse("blog_post.html", {
        "request": request,
        "user": user,
        "post": post,
        "related": related,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN BLOG ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/blog")
async def admin_blog(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    status_filter = request.query_params.get("status", "")
    q = db.query(BlogPost)
    if status_filter:
        try:
            q = q.filter(BlogPost.status == BlogPostStatus(status_filter))
        except ValueError:
            pass

    posts = q.order_by(BlogPost.created_at.desc()).all()
    for p in posts:
        _ = p.category
        _ = p.author

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    total = db.query(BlogPost).count()
    published = db.query(BlogPost).filter(BlogPost.status == BlogPostStatus.PUBLISHED).count()
    drafts = db.query(BlogPost).filter(BlogPost.status == BlogPostStatus.DRAFT).count()
    total_views = sum(p.views or 0 for p in posts)
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/blog.html", {
        "request": request,
        "user": user,
        "posts": posts,
        "categories": categories,
        "unread_alerts": unread_alerts,
        "stats": {
            "total": total,
            "published": published,
            "drafts": drafts,
            "total_views": total_views,
        },
        "filter_status": status_filter,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.get("/admin/blog/new")
async def admin_blog_new(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/blog_editor.html", {
        "request": request,
        "user": user,
        "post": None,
        "categories": categories,
        "unread_alerts": unread_alerts,
    })


@router.get("/admin/blog/{post_id}/edit")
async def admin_blog_edit(post_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        return RedirectResponse(url="/admin/blog?msg=Post+not+found&type=error")

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/blog_editor.html", {
        "request": request,
        "user": user,
        "post": post,
        "categories": categories,
        "unread_alerts": unread_alerts,
    })


@router.post("/admin/blog/create")
async def admin_blog_create(
    request: Request,
    title: str = Form(...),
    slug: str = Form(""),
    excerpt: str = Form(""),
    content: str = Form(""),
    status: str = Form("draft"),
    category_id: str = Form(""),
    featured_image: str = Form(""),
    is_featured: str = Form(""),
    tags: str = Form(""),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    final_slug = slug.strip() if slug.strip() else _slugify(title)

    # Ensure unique slug
    existing = db.query(BlogPost).filter(BlogPost.slug == final_slug).first()
    if existing:
        final_slug = f"{final_slug}-{int(datetime.utcnow().timestamp())}"

    post_status = BlogPostStatus(status) if status in [s.value for s in BlogPostStatus] else BlogPostStatus.DRAFT

    post = BlogPost(
        title=title.strip(),
        slug=final_slug,
        excerpt=excerpt.strip() or None,
        content=content,
        status=post_status,
        category_id=int(category_id) if category_id else None,
        featured_image=featured_image.strip() or None,
        is_featured=bool(is_featured),
        tags=tags.strip() or None,
        meta_title=meta_title.strip() or None,
        meta_description=meta_description.strip() or None,
        author_id=user.id,
        published_at=datetime.utcnow() if post_status == BlogPostStatus.PUBLISHED else None,
    )
    db.add(post)
    db.commit()

    action = "published" if post_status == BlogPostStatus.PUBLISHED else "saved as draft"
    return RedirectResponse(
        url=f"/admin/blog?msg=Post+{action}+successfully&type=success",
        status_code=302,
    )


@router.post("/admin/blog/{post_id}/update")
async def admin_blog_update(
    post_id: int,
    request: Request,
    title: str = Form(...),
    slug: str = Form(""),
    excerpt: str = Form(""),
    content: str = Form(""),
    status: str = Form("draft"),
    category_id: str = Form(""),
    featured_image: str = Form(""),
    is_featured: str = Form(""),
    tags: str = Form(""),
    meta_title: str = Form(""),
    meta_description: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        return RedirectResponse(url="/admin/blog?msg=Post+not+found&type=error")

    post.title = title.strip()
    if slug.strip() and slug.strip() != post.slug:
        new_slug = slug.strip()
        existing = db.query(BlogPost).filter(BlogPost.slug == new_slug, BlogPost.id != post_id).first()
        if existing:
            new_slug = f"{new_slug}-{int(datetime.utcnow().timestamp())}"
        post.slug = new_slug

    post.excerpt = excerpt.strip() or None
    post.content = content
    post.category_id = int(category_id) if category_id else None
    post.featured_image = featured_image.strip() or None
    post.is_featured = bool(is_featured)
    post.tags = tags.strip() or None
    post.meta_title = meta_title.strip() or None
    post.meta_description = meta_description.strip() or None

    new_status = BlogPostStatus(status) if status in [s.value for s in BlogPostStatus] else post.status
    if new_status == BlogPostStatus.PUBLISHED and post.status != BlogPostStatus.PUBLISHED:
        post.published_at = datetime.utcnow()
    post.status = new_status

    db.commit()

    return RedirectResponse(
        url=f"/admin/blog?msg=Post+updated+successfully&type=success",
        status_code=302,
    )


@router.post("/admin/blog/{post_id}/delete")
async def admin_blog_delete(post_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if post:
        db.delete(post)
        db.commit()

    return RedirectResponse(url="/admin/blog?msg=Post+deleted&type=success", status_code=302)


@router.post("/admin/blog/{post_id}/publish")
async def admin_blog_publish(post_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if post:
        post.status = BlogPostStatus.PUBLISHED
        if not post.published_at:
            post.published_at = datetime.utcnow()
        db.commit()

    return RedirectResponse(url="/admin/blog?msg=Post+published&type=success", status_code=302)


@router.post("/admin/blog/{post_id}/archive")
async def admin_blog_archive(post_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if post:
        post.status = BlogPostStatus.ARCHIVED
        db.commit()

    return RedirectResponse(url="/admin/blog?msg=Post+archived&type=success", status_code=302)


# ── Blog Categories ──────────────────────────────────────────────────────────

@router.get("/admin/blog/categories")
async def admin_blog_categories(request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    categories = db.query(BlogCategory).order_by(BlogCategory.name).all()
    # Count posts per category
    for cat in categories:
        cat.post_count = db.query(BlogPost).filter(BlogPost.category_id == cat.id).count()

    unread_alerts = db.query(Alert).filter(Alert.status == AlertStatus.UNREAD).count()

    return templates.TemplateResponse("admin/blog_categories.html", {
        "request": request,
        "user": user,
        "categories": categories,
        "unread_alerts": unread_alerts,
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/admin/blog/categories/create")
async def admin_blog_category_create(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    slug = _slugify(name)
    existing = db.query(BlogCategory).filter(BlogCategory.slug == slug).first()
    if existing:
        return RedirectResponse(
            url=f"/admin/blog/categories?msg=Category+already+exists&type=error",
            status_code=302,
        )

    cat = BlogCategory(name=name.strip(), slug=slug)
    db.add(cat)
    db.commit()

    return RedirectResponse(
        url="/admin/blog/categories?msg=Category+created&type=success",
        status_code=302,
    )


@router.post("/admin/blog/categories/{cat_id}/delete")
async def admin_blog_category_delete(cat_id: int, request: Request, db: Session = Depends(get_db)):
    user, redirect = _require_admin(request, db)
    if redirect:
        return redirect

    cat = db.query(BlogCategory).filter(BlogCategory.id == cat_id).first()
    if cat:
        # Unlink posts from this category
        db.query(BlogPost).filter(BlogPost.category_id == cat_id).update({"category_id": None})
        db.delete(cat)
        db.commit()

    return RedirectResponse(
        url="/admin/blog/categories?msg=Category+deleted&type=success",
        status_code=302,
    )
