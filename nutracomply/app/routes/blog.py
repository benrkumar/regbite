"""
Blog routes — public blog listing + post detail, and admin blog management.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

import nh3

from app.database import get_db
from app.routes.auth import get_current_user_from_cookie
from app.services.access_control import is_platform_admin, sync_user_role_flags
from app.models import (
    BlogPost, BlogCategory, BlogPostStatus,
    Alert, AlertStatus,
)

# Allowed HTML tags/attributes for blog content (Quill.js output)
_BLOG_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "u", "s", "a", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "code",
    "img", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td",
    "span", "div", "sup", "sub", "hr",
}
_BLOG_ALLOWED_ATTRS = {
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "span": {"class", "style"},
    "div": {"class"},
    "pre": {"class"},
    "code": {"class"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}


def _sanitize_html(html: str) -> str:
    """Sanitize HTML content, keeping safe tags for blog posts."""
    return nh3.clean(
        html,
        tags=_BLOG_ALLOWED_TAGS,
        attributes=_BLOG_ALLOWED_ATTRS,
        link_rel="noopener noreferrer",
    )

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _require_admin(request: Request, db: Session):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    sync_user_role_flags(user)
    if not is_platform_admin(user):
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
        .filter(BlogPost.status == BlogPostStatus.PUBLISHED, BlogPost.is_featured)
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
        "selected_category": request.query_params.get("category", ""),
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
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
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
        "flash_message": request.query_params.get("msg"),
        "flash_type": request.query_params.get("type", "info"),
    })


@router.post("/admin/blog/create")
async def admin_blog_create(
    request: Request,
    title: str = Form(...),
    slug: str = Form(""),
    excerpt: str = Form(""),
    content: str = Form(""),
    status: str = Form("draft"),
    action: str = Form(""),  # "publish" from the Publish Now button overrides status
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

    # "Publish Now" button overrides the status radio selection
    if action == "publish":
        status = "published"
    post_status = BlogPostStatus(status) if status in [s.value for s in BlogPostStatus] else BlogPostStatus.DRAFT

    try:
        post = BlogPost(
            title=title.strip()[:300],
            slug=final_slug,
            excerpt=excerpt.strip()[:500] if excerpt.strip() else None,
            content=_sanitize_html(content) if content.strip() else "",
            status=post_status,
            category_id=int(category_id) if category_id and category_id.isdigit() else None,
            featured_image=featured_image.strip() or None,
            is_featured=bool(is_featured),
            tags=tags.strip() or None,
            meta_title=meta_title.strip()[:300] if meta_title.strip() else None,
            meta_description=meta_description.strip()[:500] if meta_description.strip() else None,
            author_id=user.id,
            published_at=datetime.utcnow() if post_status == BlogPostStatus.PUBLISHED else None,
        )
        db.add(post)
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/blog/new?msg=Error+creating+post:+{str(e)[:120]}&type=error",
            status_code=302,
        )

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
    action: str = Form(""),  # "publish" from the Publish Now button overrides status
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

    post.title = title.strip()[:300]
    if slug.strip() and slug.strip() != post.slug:
        new_slug = slug.strip()
        existing = db.query(BlogPost).filter(BlogPost.slug == new_slug, BlogPost.id != post_id).first()
        if existing:
            new_slug = f"{new_slug}-{int(datetime.utcnow().timestamp())}"
        post.slug = new_slug

    post.excerpt = excerpt.strip()[:500] if excerpt.strip() else None
    post.content = _sanitize_html(content) if content.strip() else ""
    post.category_id = int(category_id) if category_id and category_id.isdigit() else None
    post.featured_image = featured_image.strip() or None
    post.is_featured = bool(is_featured)
    post.tags = tags.strip() or None
    post.meta_title = meta_title.strip()[:300] if meta_title.strip() else None
    post.meta_description = meta_description.strip()[:500] if meta_description.strip() else None

    # "Publish Now" button overrides the status radio selection
    if action == "publish":
        status = "published"
    new_status = BlogPostStatus(status) if status in [s.value for s in BlogPostStatus] else post.status
    if new_status == BlogPostStatus.PUBLISHED and post.status != BlogPostStatus.PUBLISHED:
        post.published_at = datetime.utcnow()
    post.status = new_status

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return RedirectResponse(
            url=f"/admin/blog/{post_id}/edit?msg=Error+saving:+{str(e)[:120]}&type=error",
            status_code=302,
        )

    return RedirectResponse(
        url="/admin/blog?msg=Post+updated+successfully&type=success",
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
            url="/admin/blog/categories?msg=Category+already+exists&type=error",
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


# ═══════════════════════════════════════════════════════════════════════════════
# BLOG IMAGE UPLOAD
# ═══════════════════════════════════════════════════════════════════════════════

BLOG_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
BLOG_IMAGE_MAX_SIZE = 5 * 1024 * 1024  # 5 MB


@router.post("/admin/blog/upload-image")
async def admin_blog_upload_image(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload an image for blog posts. Returns JSON with the image URL."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    suffix = Path(file.filename).suffix.lower()
    if suffix not in BLOG_IMAGE_EXTENSIONS:
        return JSONResponse(
            {"error": f"Unsupported format. Allowed: {', '.join(BLOG_IMAGE_EXTENSIONS)}"},
            status_code=400,
        )

    content = await file.read()
    if len(content) > BLOG_IMAGE_MAX_SIZE:
        return JSONResponse({"error": "Image too large. Max 5 MB."}, status_code=400)

    # Save to static/blog-images/
    upload_dir = Path(__file__).parent.parent / "static" / "blog-images"
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{uuid.uuid4().hex}{suffix}"
    file_path = upload_dir / file_name

    with open(file_path, "wb") as f:
        f.write(content)

    return JSONResponse({"url": f"/static/blog-images/{file_name}"})


# ═══════════════════════════════════════════════════════════════════════════════
# AI-GENERATED SEO
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/admin/blog/generate-seo")
async def admin_blog_generate_seo(
    request: Request,
    db: Session = Depends(get_db),
):
    """Generate SEO meta title, description, and excerpt using AI."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    title = body.get("title", "")
    content_text = body.get("content", "")

    if not title.strip():
        return JSONResponse({"error": "Title is required"}, status_code=400)

    # Strip HTML tags for content
    import re
    clean_content = re.sub(r'<[^>]+>', '', content_text)[:3000]

    prompt = f"""Generate SEO metadata for a blog post on an FSSAI compliance platform (RegBite).

Blog title: {title}
Blog content (excerpt): {clean_content[:1500]}

Return a JSON object with:
- "meta_title": SEO-optimized title (50-60 chars, include primary keyword)
- "meta_description": SEO meta description (150-160 chars, compelling, include keywords)
- "excerpt": Blog excerpt for listing pages (100-200 chars, engaging summary)
- "tags": Comma-separated relevant tags (3-6 tags, lowercase)

Focus on FSSAI compliance, Indian food regulation, nutraceutical industry keywords.
Return ONLY valid JSON, no markdown."""

    from app.config import get_settings
    settings = get_settings()

    result = None

    # Try Claude first
    if settings.anthropic_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            import json
            result = json.loads(raw)
        except Exception as e:
            print(f"[blog-seo] Claude failed: {e}")

    # Fallback: Gemini
    if not result and settings.gemini_api_key:
        try:
            import google.generativeai as genai
            import json
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            result = json.loads(raw)
        except Exception as e:
            print(f"[blog-seo] Gemini failed: {e}")

    if not result:
        return JSONResponse({"error": "AI generation failed. Check API keys."}, status_code=500)

    return JSONResponse(result)
