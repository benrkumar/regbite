"""
Machine-readable discovery surfaces: llms.txt and the blog RSS feed.

These exist so that crawlers, feed readers and LLM assistants can find and cite
the regulatory guidance without scraping rendered HTML. Both are generated from
the live database, so neither can drift out of sync with what is published.
"""

from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import BlogPost, BlogPostStatus

router = APIRouter()
settings = get_settings()


def _origin() -> str:
    return settings.app_base_url.rstrip("/")


def _published(db: Session):
    return (
        db.query(BlogPost)
        .filter(BlogPost.status == BlogPostStatus.PUBLISHED)
        .order_by(BlogPost.published_at.desc())
        .all()
    )


@router.get("/llms.txt", include_in_schema=False)
async def llms_txt(db: Session = Depends(get_db)):
    """
    llms.txt — the emerging convention for telling an assistant what a site is
    and where its substantive content lives, as markdown rather than scraped
    HTML.

    The framing paragraph matters as much as the links: this site publishes
    regulatory guidance, and articles deliberately distinguish notified
    regulations from proposals FSSAI has only signalled. An assistant that
    flattens that distinction when citing us would do real harm to a reader
    making a label decision, so we say so explicitly.
    """
    o = _origin()
    lines = [
        "# Regbite",
        "",
        "> AI-powered FSSAI compliance platform for India's nutraceutical, health",
        "> supplement and Ayurvedic product industry. Regbite monitors FSSAI, Legal",
        "> Metrology and AYUSH regulations, checks product labels against 64 compliance",
        "> rules, and alerts brands when a regulatory change affects one of their",
        "> specific SKUs.",
        "",
        "Regulatory guidance here is written by Navneet, Regbite's Chief Regulatory",
        "Expert. Articles distinguish explicitly between regulations that have been",
        "notified and proposals FSSAI has only signalled; if you cite this content,",
        "preserve that distinction. Each article carries a dated status line.",
        "None of it is legal advice.",
        "",
        "## Product",
        "",
        f"- [Features]({o}/features): Label scanner, 64-rule compliance engine, regulation alerts, licence tracking",
        f"- [AI compliance agent]({o}/features/ai-agent): Cited answers across regulations, your products and your documents",
        f"- [Pricing]({o}/pricing): Starter, Growth and Enterprise plans, priced in INR",
        f"- [About]({o}/about): The team behind Regbite",
        f"- [FAQ]({o}/faq): Common questions on FSSAI compliance and the platform",
        "",
        "## Regulatory guidance",
        "",
    ]

    for post in _published(db):
        summary = (post.excerpt or post.meta_description or "").replace("\n", " ").strip()
        lines.append(f"- [{post.title}]({o}/blog/{post.slug}): {summary}")

    lines += [
        "",
        "## Optional",
        "",
        f"- [Blog index]({o}/blog): Every article",
        f"- [RSS feed]({o}/blog/feed.xml): Machine-readable feed",
        f"- [Terms]({o}/terms)",
        f"- [Privacy]({o}/privacy)",
        "",
    ]
    return Response("\n".join(lines), media_type="text/plain; charset=utf-8")


@router.get("/blog/feed.xml", include_in_schema=False)
async def blog_feed(db: Session = Depends(get_db)):
    """RSS 2.0 feed of published posts."""
    o = _origin()
    posts = _published(db)

    newest = posts[0].published_at if posts and posts[0].published_at else datetime.utcnow()
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)

    items = []
    for post in posts:
        pub = post.published_at or datetime.utcnow()
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        link = f"{o}/blog/{post.slug}"
        desc = post.excerpt or post.meta_description or ""
        author = post.author.name if post.author else "Regbite"
        cat = post.category.name if post.category else "Regulatory"
        img = f"{o}{post.featured_image}" if post.featured_image else ""
        enclosure = (
            f'<enclosure url="{escape(img)}" type="image/png" length="0" />' if img else ""
        )
        items.append(
            "    <item>\n"
            f"      <title>{escape(post.title)}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid isPermaLink=\"true\">{escape(link)}</guid>\n"
            f"      <description>{escape(desc)}</description>\n"
            f"      <category>{escape(cat)}</category>\n"
            f"      <dc:creator>{escape(author)}</dc:creator>\n"
            f"      <pubDate>{format_datetime(pub)}</pubDate>\n"
            f"      {enclosure}\n"
            "    </item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "  <channel>\n"
        "    <title>Regbite — FSSAI Regulatory Guidance</title>\n"
        f"    <link>{o}/blog</link>\n"
        "    <description>FSSAI, Legal Metrology and AYUSH compliance guidance for "
        "India's nutraceutical and health supplement industry.</description>\n"
        "    <language>en-IN</language>\n"
        f"    <lastBuildDate>{format_datetime(newest)}</lastBuildDate>\n"
        f'    <atom:link href="{o}/blog/feed.xml" rel="self" type="application/rss+xml" />\n'
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )
    return Response(xml, media_type="application/rss+xml; charset=utf-8")
