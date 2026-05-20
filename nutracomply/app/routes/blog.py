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
                model="claude-haiku-4-5",
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

    if not result:
        return JSONResponse({"error": "AI generation failed. Check API keys."}, status_code=500)

    return JSONResponse(result)


# ═══════════════════════════════════════════════════════════════════════════════
# SEED BLOG ARTICLES (one-time admin endpoint)
# ═══════════════════════════════════════════════════════════════════════════════

_SEED_ARTICLES = [
    {
        "title": "The FSSAI Show-Cause Notice Survival Guide: What to Do in the First 72 Hours",
        "slug": "fssai-show-cause-notice-survival-guide",
        "cat": ("FSSAI Compliance", "fssai-compliance"),
        "tags": "FSSAI, show-cause notice, SCN, compliance, enforcement",
        "meta_title": "FSSAI Show-Cause Notice Guide — What to Do in 72 Hours | RegBite",
        "meta_description": "Received an FSSAI show-cause notice? Here is exactly what to do in the first 72 hours — from Navneet, RegBite's Chief Regulatory Expert.",
        "excerpt": "In 2024, FSSAI issued 34% more show-cause notices to nutraceutical manufacturers than in 2023. This article tells you what to do if you receive one — and how to make sure you never do.",
        "content": """<h2>First: What Exactly Is a Show-Cause Notice?</h2>
<p>A show-cause notice (SCN) from FSSAI is a formal regulatory action requiring you to explain why the authority should not take enforcement action against your business. It is not a prosecution. It is not a fine. It is a notice requiring a response — and your response determines everything that happens next.</p>
<p>The most common trigger for an SCN in the nutraceutical space: a label that carries a health claim FSSAI has not approved, an ingredient quantity that exceeds Schedule IV limits, or an expired FoSCoS licence.</p>
<h2>Hour 0–24: Read the Notice Carefully</h2>
<ul>
<li>Identify the specific regulation cited — every SCN must reference the specific section of the FSS Act or Regulations violated</li>
<li>Note the response deadline — most SCNs give 30 days to respond. Some give 15. A few give 7. Missing this deadline converts an SCN into an automatic enforcement action.</li>
<li>Identify whether it is a label complaint, a product formulation issue, or a manufacturing/hygiene violation — the response strategy differs</li>
<li>Do NOT respond immediately — your first response will become part of the official record</li>
</ul>
<h2>Hour 24–48: Gather Your Documentation</h2>
<p>The strength of your SCN response depends entirely on documentation. FSSAI enforcement officers are looking for evidence that you: (a) knew about the regulation, (b) took proactive steps to comply, and (c) have a clear remediation plan.</p>
<ul>
<li>Pull your most recent gap report — if you used Regbite, this shows you were actively monitoring compliance</li>
<li>Pull your batch records for the affected product(s)</li>
<li>Pull the label approval correspondence if available</li>
<li>Pull your ingredient COAs (Certificates of Analysis) to verify actual quantities vs label claims</li>
</ul>
<h2>Hour 48–72: Draft Your Response</h2>
<p>A good SCN response has four elements: acknowledgement, explanation, remediation, and prevention.</p>
<ul>
<li><strong>Acknowledgement</strong> — confirm receipt of the notice and your understanding of the violation cited</li>
<li><strong>Explanation</strong> — if the violation was technical or based on a misunderstanding of the regulation, explain clearly with supporting documents</li>
<li><strong>Remediation</strong> — describe specifically what corrective action you have taken or will take, with timeline</li>
<li><strong>Prevention</strong> — describe what system you have put in place to prevent recurrence.</li>
</ul>
<blockquote><strong>IMPORTANT:</strong> Never admit to intentional non-compliance in an SCN response. Always frame violations as unintentional and demonstrate good faith remediation. Consult a food law attorney before submitting your response to any FSSAI enforcement action.</blockquote>
<h2>How Regbite Helps — Before and After</h2>
<p><strong>Before an SCN:</strong> Regbite's daily regulatory monitoring catches the type of violation that triggers SCNs — label claims FSSAI has not approved, ingredient quantities approaching Schedule IV limits — before an inspector ever visits. Your gap report is your early warning system.</p>
<p><strong>After an SCN:</strong> Regbite's gap report history shows FSSAI that you were actively monitoring compliance before the notice was issued. This is evidence of good faith — the single most powerful factor in how FSSAI handles your response.</p>
<p><strong>Stop waiting for the notice. Start monitoring.</strong> Generate your free gap report. See your compliance gaps before FSSAI does.</p>""",
    },
    {
        "title": "Schedule IV Changed Again. Is Your Ashwagandha Product Still Compliant?",
        "slug": "schedule-iv-ashwagandha-compliance",
        "cat": ("Schedule IV", "schedule-iv"),
        "tags": "Schedule IV, Ashwagandha, FSSAI, nutraceutical, compliance",
        "meta_title": "Schedule IV Ashwagandha Compliance — Is Your Product Still Legal? | RegBite",
        "meta_description": "FSSAI's Schedule IV has been amended 12 times in 18 months. Is your nutraceutical product still compliant? Regbite checks your portfolio automatically.",
        "excerpt": "FSSAI's Schedule IV is the most important and most frequently amended regulation for nutraceutical manufacturers. It governs every botanical ingredient — and it changes without warning.",
        "content": """<p>FSSAI's Schedule IV is the most important and most frequently amended regulation for nutraceutical manufacturers. It governs every botanical ingredient — Ashwagandha, Turmeric, Brahmi, Moringa, Collagen, Probiotics — and it changes without warning.</p>
<p>In the last 18 months, FSSAI has issued 12 amendments to Schedule IV. Most manufacturers we speak to are aware of 3 of them.</p>
<h2>What Schedule IV Actually Governs</h2>
<p>Schedule IV sets the rules for health supplements and nutraceuticals that contain plant-based or bioactive ingredients. For each ingredient, it defines: the maximum permitted quantity per serving, the permitted forms (powder, extract, standardised extract — they are not interchangeable), and any consumer-specific restrictions (not for children, not during pregnancy, physician advisory requirements).</p>
<p>A manufacturer who uses Ashwagandha root powder is operating under different rules than one who uses a standardised 5% Withanolide extract. The form matters as much as the quantity.</p>
<h2>The Top 5 Schedule IV Violations We See</h2>
<h3>1. Ashwagandha above 600mg/day</h3>
<p>The current limit is 600mg standardised extract per day. We regularly see products claiming 750mg, 900mg, or 1,000mg. Each one is non-compliant.</p>
<h3>2. Using 'proprietary blend' to avoid declaring individual quantities</h3>
<p>FSSAI requires individual ingredient quantities in nutraceutical products. A proprietary blend declaration does not exempt you from Schedule IV quantity limits.</p>
<h3>3. Ignoring the 'not for children under 12' restriction</h3>
<p>Many Schedule IV ingredients carry mandatory consumer restrictions. Failing to display them on the label is a labelling violation on top of any formulation issue.</p>
<h3>4. Collagen without declaring the source</h3>
<p>Fish-derived, bovine-derived, and plant-derived collagen have different regulatory treatments. The source must be declared. Many products simply say 'Collagen Peptides' without specifying.</p>
<h3>5. Probiotics with CFU count at manufacture, not end of shelf life</h3>
<p>FSSAI requires CFU count to be guaranteed at the end of shelf life — not at manufacture. A product with 10 billion CFU at manufacture might have 2 billion by expiry.</p>
<blockquote><strong>CHECK THIS NOW:</strong> Open your formulation sheet. Find every Schedule IV ingredient. Cross-check the quantity and form against the current Schedule IV text. If you have not done this in the last 6 months, you may have a gap you do not know about.</blockquote>
<p><strong>Run your Schedule IV compliance check in 3 minutes.</strong> Regbite checks every ingredient in every SKU against current Schedule IV automatically.</p>""",
    },
    {
        "title": "Why We Deliver FSSAI Compliance Alerts on WhatsApp — Not Email",
        "slug": "whatsapp-vs-email-fssai-alerts",
        "cat": ("Product", "product"),
        "tags": "WhatsApp, FSSAI alerts, compliance, notifications, product",
        "meta_title": "WhatsApp vs Email for FSSAI Alerts — Why WhatsApp Wins | RegBite",
        "meta_description": "Email has a 22% open rate. WhatsApp has 98%. When FSSAI gives you 30 days to respond, which channel do you trust? RegBite delivers alerts on WhatsApp.",
        "excerpt": "When we were designing Regbite's alert system, the easy choice was email. We chose WhatsApp instead. Here is why — and why it matters for your compliance.",
        "content": """<h2>The Numbers That Changed Our Thinking</h2>
<ul>
<li>Average email open rate in India: 22%. That means 78% of compliance alerts sent by email are never read.</li>
<li>Average WhatsApp message open rate: 98%. That means 98% of compliance alerts sent on WhatsApp are read — typically within 3 minutes.</li>
<li>FSSAI enforcement actions have a 30-day response window on average. A compliance alert that sits in an email inbox for 2 weeks has already consumed half that window.</li>
</ul>
<h2>Why Email Fails for Compliance</h2>
<p>Compliance alerts are not marketing emails. They are time-sensitive operational information that requires action. Email has trained us to batch-process and defer. WhatsApp has trained us to read and respond immediately.</p>
<p>A nutraceutical founder who is travelling, at a production meeting, or at a trade show will check their WhatsApp. They will not check their email. By the time they read the email alert, three competitors who were also affected by the same Schedule IV change may have already called their formulation team.</p>
<h2>What Our WhatsApp Alerts Actually Look Like</h2>
<blockquote>
<p><strong>Regbite Alert — CRITICAL</strong></p>
<p>FSSAI has updated Schedule IV: Maximum permitted Ashwagandha (as standardised extract) reduced to 600mg/day effective immediately.</p>
<p>Your affected SKU: AshwaMax 900 | Current formulation: 900mg/serving | Action required: Reformulate or relabel before next batch.</p>
<p>Tap to view your gap report.</p>
<p>Source: FSSAI Circular No. FSSAI-REG-2025-IV-008</p>
</blockquote>
<p>That message takes 20 seconds to read. It names your specific product. It tells you the action required. It links directly to your gap report. No login required. No dashboard navigation. Just the information you need and a direct link to the next step.</p>
<h2>See What Your First WhatsApp Alert Would Say</h2>
<p>Sign up. Enter your SKUs. We will run your first compliance check and tell you which alerts you would have received in the last 30 days.</p>""",
    },
    {
        "title": "The Hidden Cost of Manual FSSAI Compliance Tracking (It Is More Than Your Consultant Bill)",
        "slug": "hidden-cost-manual-fssai-compliance",
        "cat": ("ROI", "roi"),
        "tags": "ROI, compliance cost, FSSAI, consultant, nutraceutical",
        "meta_title": "Hidden Cost of Manual FSSAI Compliance — Full Cost Breakdown | RegBite",
        "meta_description": "Manual FSSAI compliance costs ₹3L–₹19.3L/year when you add consultant fees, label reprints, penalties, and lost sales. RegBite Growth plan: ₹2,09,999/year.",
        "excerpt": "Most nutraceutical founders think their FSSAI compliance spend is their consultant's retainer. But when we ask them to calculate the full cost, the number is always significantly larger.",
        "content": """<p>Most nutraceutical founders who talk to us say their FSSAI compliance spend is their consultant's retainer — typically ₹8,000–₹15,000 per visit, two to three times per year. ₹24,000–₹45,000 annually. Manageable.</p>
<p>But when we ask them to calculate the full cost of manual compliance, the number is always significantly larger. Here is the calculation most founders have never run.</p>
<h2>The True Cost of Manual FSSAI Compliance</h2>
<table>
<thead><tr><th>Cost Category</th><th>Annual Estimate</th><th>Notes</th></tr></thead>
<tbody>
<tr><td>FSSAI consultant retainer / visits</td><td>₹24,000–₹60,000</td><td>2–4 visits per year at ₹8,000–₹15,000 per visit</td></tr>
<tr><td>Internal team time monitoring FSSAI</td><td>₹60,000–₹1,20,000</td><td>1 hour/week at a senior manager's salary</td></tr>
<tr><td>Label reprints due to compliance errors</td><td>₹15,000–₹2,00,000</td><td>One reprint per year at ₹15K minimum. Major reprints cost ₹2L+</td></tr>
<tr><td>FoSCoS renewal penalty (if missed)</td><td>₹5,000–₹50,000</td><td>Late renewal penalties range from ₹5,000 to licence suspension</td></tr>
<tr><td>Product withdrawal / destruction costs</td><td>₹50,000–₹5,00,000</td><td>One non-compliant batch catch at retail = full destruction</td></tr>
<tr><td>Legal fees for SCN response</td><td>₹50,000–₹2,00,000</td><td>Average food law attorney response: ₹50,000–₹2L per SCN</td></tr>
<tr><td>Lost sales during SCN / inspection period</td><td>₹1,00,000–₹10,00,000</td><td>Retailers pause orders when FSSAI action is known</td></tr>
<tr><td><strong>TOTAL ANNUAL EXPOSURE</strong></td><td><strong>₹3,04,000–₹19,30,000</strong></td><td>Conservative to severe scenario</td></tr>
</tbody>
</table>
<h2>The Math Is Simple</h2>
<p>Regbite's Growth plan costs ₹2,09,999 per year. Against a conservative exposure of ₹3 lakh, Regbite breaks even in the first year. Against a severe scenario — one withdrawn batch, one SCN, one lost retail partnership — it pays back 10x.</p>
<h2>Run Your Compliance Cost Calculation</h2>
<p>We will send you a personalised cost analysis based on your portfolio size and product categories.</p>""",
    },
]


@router.post("/admin/blog/seed-articles")
async def admin_blog_seed_articles(request: Request, db: Session = Depends(get_db)):
    """One-time endpoint to seed the 4 docx blog articles."""
    user, redirect = _require_admin(request, db)
    if redirect:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    created, skipped = [], []
    for art in _SEED_ARTICLES:
        existing = db.query(BlogPost).filter(BlogPost.slug == art["slug"]).first()
        if existing:
            skipped.append(art["slug"])
            continue

        cat_name, cat_slug = art["cat"]
        cat = db.query(BlogCategory).filter(BlogCategory.slug == cat_slug).first()
        if not cat:
            cat = BlogCategory(name=cat_name, slug=cat_slug)
            db.add(cat)
            db.flush()

        post = BlogPost(
            title=art["title"],
            slug=art["slug"],
            excerpt=art["excerpt"],
            content=art["content"],
            status=BlogPostStatus.PUBLISHED,
            category_id=cat.id,
            author_id=user.id,
            tags=art["tags"],
            meta_title=art["meta_title"],
            meta_description=art["meta_description"],
            is_featured=False,
            published_at=datetime.utcnow(),
        )
        db.add(post)
        db.flush()
        created.append(art["slug"])

    db.commit()
    return JSONResponse({
        "created": created,
        "skipped": skipped,
        "message": f"{len(created)} articles published, {len(skipped)} already existed",
    })
