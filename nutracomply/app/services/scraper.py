"""
Regulation discovery and document parsing helpers.

The ingestion layer uses this module for three distinct stages:
1. Discover candidate regulation links from a configured source page
2. Accept/reject a candidate using source-aware heuristics
3. Download the full document, hash it, and extract text/page counts
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.config import get_settings

settings = get_settings()

FSSAI_REGULATIONS_URL = "https://fssai.gov.in/cms/food-safety-and-standards-regulations.php"
FSSAI_GAZETTE_URL = "https://fssai.gov.in/notifications.php?notification=gazette-notification"
AYUSH_ADVISORIES_URL = "https://ayush.gov.in/advisories"
AYUSH_REGULATIONS_URL = "https://ayush.gov.in/regulation-rules-and-acts"
LEGAL_METROLOGY_URL = "https://consumeraffairs.nic.in/policies-rules/legal-metrology-packaged-commodities-rules-2011"
LEGAL_METROLOGY_ACT_URL = "https://consumeraffairs.gov.in/pages/legal-metrology-act"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_REGULATION_KEYWORDS = [
    "regulation",
    "amendment",
    "notification",
    "gazette",
    "order",
    "act",
    "rule",
    "standard",
    "advisory",
    "direction",
    "guideline",
    "labelling",
    "labeling",
    "packaged commodit",
    "food safety",
    "nutraceutical",
    "health supplement",
    "ayurved",
    "prohibition",
    "restriction",
    "schedule",
    "annex",
    "draft",
    "final",
    "notifi",
]

_REJECT_PATTERNS = [
    "brochure",
    "application form",
    "application format",
    "recruitment",
    "tender",
    "vacancy",
    "career",
    "manual",
    "training",
    "annual report",
    "annual-report",
    "newsletter",
    "magazine",
    "photo",
    "gallery",
    "logo",
    "banner",
    "infographic",
    "rti",
    "right to information",
    "grievance",
    "feedback form",
    "login",
    "register",
    "signup",
    "download app",
    "organisat",
    "organigram",
    "staff list",
    "telephone directory",
    "visitor",
    "contact us",
    "sitemap",
    "faq",
    "empanelment",
    "vendor",
    "quotation",
    "e-tender",
    "citizen charter",
    "citizen-charter",
]

_GENERIC_PATH_STEMS = {
    "",
    "download",
    "view",
    "index",
    "default",
    "notification",
    "notifications",
    "cms",
    "page",
    "document",
}

DEFAULT_SOURCE_DISCOVERY_CONFIG: dict[str, dict[str, Any]] = {
    "fssai-regulations": {
        "section": "regulations",
        "document_keywords": ["regulation", "amendment", "notification", "labelling"],
        "max_documents": 200,
        "pdf_page_cap": 200,
        "max_text_chars": 20000,
        "source_family": "fssai",
    },
    "fssai-gazette": {
        "section": "gazette_notification",
        "document_keywords": ["gazette", "notification", "regulation", "amendment"],
        "max_documents": 200,
        "pdf_page_cap": 200,
        "max_text_chars": 20000,
        "source_family": "fssai",
    },
    "ayush-advisories": {
        "section": "ayush",
        "document_keywords": ["advisory", "notification", "circular", "guideline"],
        "max_documents": 100,
        "pdf_page_cap": 200,
        "max_text_chars": 20000,
        "source_family": "ayush",
    },
    "ayush-regulations": {
        "section": "ayush",
        "document_keywords": ["regulation", "rule", "act", "guideline"],
        "max_documents": 100,
        "pdf_page_cap": 200,
        "max_text_chars": 20000,
        "source_family": "ayush",
    },
    "legal-metrology-rules": {
        "section": "legal_metrology",
        "document_keywords": ["packaged", "metrology", "rule", "amendment", "notification"],
        "max_documents": 100,
        "pdf_page_cap": 200,
        "max_text_chars": 20000,
        "source_family": "legal_metrology",
    },
    "legal-metrology-act": {
        "section": "legal_metrology",
        "document_keywords": ["metrology", "act", "rule", "notification"],
        "max_documents": 100,
        "pdf_page_cap": 200,
        "max_text_chars": 20000,
        "source_family": "legal_metrology",
    },
}


@dataclass
class SourceDiscovery:
    source_url: str
    document_name: str
    source_document_key: str
    document_type: str | None = None
    section: str | None = None


@dataclass
class DownloadedDocument:
    text: str
    sha256: str
    total_pages: int | None
    extracted_pages: int | None
    content_type: str | None


def get_default_source_config(slug: str) -> dict[str, Any]:
    return dict(DEFAULT_SOURCE_DISCOVERY_CONFIG.get(slug, {}))


def build_source_document_key(source_slug: str, url: str, document_name: str | None) -> str:
    parsed = urlparse(url)
    path_stem = Path(parsed.path).stem.strip().lower()
    if path_stem and path_stem not in _GENERIC_PATH_STEMS:
        token = _slugify_token(path_stem)
        if token:
            return f"{source_slug}:{token}"

    if document_name:
        token = _slugify_token(document_name)
        if token:
            return f"{source_slug}:{token}"

    fallback = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"{source_slug}:{fallback}"


def resolve_source_family_slug(source_slug: str | None) -> str:
    slug = (source_slug or "").lower()
    if slug.startswith("ayush"):
        return "ayush"
    if slug.startswith("legal-metrology"):
        return "legal_metrology"
    return "fssai"


def discover_documents_for_source(source) -> list[SourceDiscovery]:
    config = _source_config(source)
    try:
        response = httpx.get(
            source.base_url,
            headers=HEADERS,
            timeout=30,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Source fetch failed for {source.slug}: {exc}") from exc

    soup = _make_soup(response.text)
    discoveries: list[SourceDiscovery] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = (link.get("href") or "").strip()
        if not href:
            continue
        name = link.get_text(strip=True) or Path(urlparse(href).path).name or "Untitled document"
        if not _is_document_candidate(href, name, config):
            continue
        full_url = _resolve_url(href, source.base_url)
        if full_url in seen:
            continue
        seen.add(full_url)
        discoveries.append(
            SourceDiscovery(
                source_url=full_url,
                document_name=name[:500],
                source_document_key=build_source_document_key(source.slug, full_url, name),
                document_type=config.get("document_type") or getattr(source, "doc_type", None),
                section=config.get("section"),
            )
        )

    limit = int(config.get("max_documents") or 200)
    return discoveries[:limit]


def evaluate_discovery(source, discovery: SourceDiscovery) -> tuple[bool, str | None]:
    config = _source_config(source)
    combined = f"{discovery.source_url} {discovery.document_name}".lower()

    for pattern in config.get("reject_patterns", []):
        if pattern.lower() in combined:
            return False, f"Rejected by source-specific pattern '{pattern}'"

    if _is_regulation_document(discovery.source_url, discovery.document_name):
        return True, None

    return False, "Link did not match regulation-document heuristics"


def download_document(
    url: str,
    *,
    max_pdf_pages: int | None = None,
    max_text_chars: int = 20000,
) -> Optional[DownloadedDocument]:
    try:
        response = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        print(f"[scraper] Download failed {url}: {exc}")
        return None

    content = response.content
    sha256 = hashlib.sha256(content).hexdigest()
    content_type = response.headers.get("content-type", "")

    if url.lower().endswith(".pdf") or "application/pdf" in content_type:
        text, total_pages, extracted_pages = _extract_pdf_text_from_bytes(
            content,
            max_pages=max_pdf_pages,
            max_chars=max_text_chars,
        )
    else:
        soup = _make_soup(content)
        text = soup.get_text(separator="\n", strip=True)[:max_text_chars]
        total_pages = 1
        extracted_pages = 1 if text else 0

    return DownloadedDocument(
        text=text or "",
        sha256=sha256,
        total_pages=total_pages,
        extracted_pages=extracted_pages,
        content_type=content_type or None,
    )


def download_and_hash(url: str) -> tuple[Optional[str], Optional[str]]:
    doc = download_document(url)
    if not doc:
        return None, None
    return doc.text, doc.sha256


def scrape_fssai_pages() -> list[dict[str, str]]:
    """Compatibility wrapper used by older jobs."""
    source_specs = [
        {
            "slug": "fssai-regulations",
            "base_url": FSSAI_REGULATIONS_URL,
            "doc_type": "regulation_page",
        },
        {
            "slug": "fssai-gazette",
            "base_url": FSSAI_GAZETTE_URL,
            "doc_type": "gazette",
        },
        {
            "slug": "ayush-advisories",
            "base_url": AYUSH_ADVISORIES_URL,
            "doc_type": "advisory",
        },
        {
            "slug": "ayush-regulations",
            "base_url": AYUSH_REGULATIONS_URL,
            "doc_type": "regulation_page",
        },
        {
            "slug": "legal-metrology-rules",
            "base_url": LEGAL_METROLOGY_URL,
            "doc_type": "rules",
        },
        {
            "slug": "legal-metrology-act",
            "base_url": LEGAL_METROLOGY_ACT_URL,
            "doc_type": "act",
        },
    ]
    results: list[dict[str, str]] = []
    for spec in source_specs:
        source = type("CompatSource", (), {
            "slug": spec["slug"],
            "base_url": spec["base_url"],
            "doc_type": spec["doc_type"],
            "discovery_config": get_default_source_config(spec["slug"]),
        })()
        try:
            results.extend(
                {
                    "source_url": item.source_url,
                    "document_name": item.document_name,
                    "section": item.section or "",
                }
                for item in discover_documents_for_source(source)
            )
        except Exception as exc:
            print(f"[scraper] Discovery error for {spec['slug']}: {exc}")
    return results


def _is_document_candidate(href: str, link_text: str, config: dict[str, Any]) -> bool:
    href_lower = href.lower()
    text_lower = (link_text or "").lower().strip()
    combined = f"{href_lower} {text_lower}"
    keywords = [str(item).lower() for item in config.get("document_keywords", [])]

    if href_lower.endswith(".pdf"):
        return True

    if any(keyword in combined for keyword in keywords):
        return True

    return any(keyword in combined for keyword in _REGULATION_KEYWORDS)


def _is_regulation_document(url: str, link_text: str) -> bool:
    url_lower = url.lower()
    text_lower = (link_text or "").lower().strip()
    combined = f"{url_lower} {text_lower}"

    if any(pattern in combined for pattern in _REJECT_PATTERNS):
        return False

    if any(keyword in combined for keyword in _REGULATION_KEYWORDS):
        return True

    return False


def _resolve_url(href: str, base_url: str) -> str:
    return urljoin(base_url, href)


def _make_soup(content):
    from bs4 import BeautifulSoup

    return BeautifulSoup(content, "lxml")


def _source_config(source) -> dict[str, Any]:
    config = get_default_source_config(getattr(source, "slug", ""))
    custom = getattr(source, "discovery_config", None) or {}
    config.update(custom)
    config.setdefault("document_type", getattr(source, "doc_type", None))
    return config


def _slugify_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    token = token.strip("-")
    return token[:180]


def _extract_pdf_text_from_bytes(
    content: bytes,
    *,
    max_pages: int | None = None,
    max_chars: int = 20000,
) -> tuple[str, Optional[int], Optional[int]]:
    try:
        import io

        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            total_pages = len(pdf.pages)
            pages = pdf.pages[:max_pages] if max_pages else pdf.pages
            extracted_pages = 0
            parts: list[str] = []
            chars_used = 0

            for page in pages:
                extracted_pages += 1
                page_text = page.extract_text() or ""
                if not page_text:
                    continue
                remaining = max_chars - chars_used
                if remaining <= 0:
                    break
                if len(page_text) > remaining:
                    parts.append(page_text[:remaining])
                    chars_used = max_chars
                    break
                parts.append(page_text)
                chars_used += len(page_text)

        return "\n".join(parts), total_pages, extracted_pages
    except Exception as exc:
        print(f"[scraper] PDF text extraction failed: {exc}")
        return "", None, None


def classify_regulation_change(document_name: str, text_excerpt: str) -> dict:
    """
    Uses Gemini to classify the type and severity of a regulation change.
    Falls back to keyword heuristics if Gemini is unavailable.
    """
    if settings.gemini_api_key:
        try:
            return _classify_with_gemini(document_name, text_excerpt)
        except Exception as exc:
            print(f"[scraper] Gemini classification failed: {exc}")

    return _classify_with_keywords(document_name, text_excerpt)


CLASSIFICATION_PROMPT = """
You are an FSSAI (Food Safety and Standards Authority of India) regulatory expert.

Analyze this regulatory document excerpt and classify it.

Document name: {name}
Text excerpt:
---
{text}
---

Return ONLY valid JSON (no markdown):
{{
  "change_type": one of ["INGREDIENT_BAN", "INGREDIENT_RESTRICTION", "LABEL_REQUIREMENT",
                          "HEALTH_CLAIM", "FORMAT_CHANGE", "NEW_REGULATION", "AMENDMENT", "UNKNOWN"],
  "severity": one of ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
  "summary_text": "1-2 sentence plain English summary of what changed",
  "affected_categories": list of affected areas like ["nutraceuticals", "health supplements", "labelling", "ingredients"],
  "effective_date": "date string if mentioned, else null"
}}
"""


def _classify_with_gemini(name: str, text: str) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
    prompt = CLASSIFICATION_PROMPT.format(name=name, text=text[:3000])
    response = model.generate_content(prompt, generation_config={"temperature": 0.1})
    raw = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def suggest_rule_modifications(document_name: str, text_excerpt: str, existing_rules: list[dict]) -> list[dict]:
    """
    When a CRITICAL regulation change is detected, use LLM to suggest
    rule modifications or new rules that should be added to the compliance engine.
    Returns list of suggested rule changes.
    """
    if not settings.gemini_api_key:
        return []

    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

        rules_summary = "\n".join(
            f"- {rule['rule_code']}: {rule['description'][:100]}"
            for rule in existing_rules[:30]
        )

        prompt = (
            "You are an FSSAI regulatory compliance engineer.\n\n"
            f"A CRITICAL regulation change has been detected:\n"
            f"Document: {document_name}\n"
            f"Content excerpt:\n{text_excerpt[:2000]}\n\n"
            f"Current compliance rules in our engine:\n{rules_summary}\n\n"
            "Based on this regulation change, suggest specific modifications to existing rules "
            "or new rules that should be added. Return ONLY valid JSON array (no markdown):\n"
            '[{"action": "UPDATE" or "ADD", "rule_code": "existing or suggested code", '
            '"field": "field to change", '
            '"old_value": "current value if UPDATE", '
            '"new_value": "suggested new value", '
            '"reason": "why this change is needed"}]\n\n'
            "Return empty array [] if no changes needed."
        )

        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 1024},
        )
        raw = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as exc:
        print(f"[scraper] Rule modification suggestion failed: {exc}")
        return []


def _classify_with_keywords(name: str, text: str) -> dict:
    combined = f"{name} {text}".lower()

    change_type = "UNKNOWN"
    severity = "MEDIUM"

    if any(word in combined for word in ["ban", "prohibited", "not permitted", "remove from"]):
        change_type = "INGREDIENT_BAN"
        severity = "CRITICAL"
    elif any(word in combined for word in ["restrict", "limit", "maximum daily", "dosage limit"]):
        change_type = "INGREDIENT_RESTRICTION"
        severity = "HIGH"
    elif any(word in combined for word in ["label", "labelling", "labeling", "declaration", "marking", "font"]):
        change_type = "LABEL_REQUIREMENT"
        severity = "HIGH"
    elif any(word in combined for word in ["health claim", "claim", "structure function"]):
        change_type = "HEALTH_CLAIM"
        severity = "MEDIUM"
    elif any(word in combined for word in ["new regulation", "notified", "gazette"]):
        change_type = "NEW_REGULATION"
        severity = "HIGH"
    elif any(word in combined for word in ["amend", "amendment", "revised", "updated"]):
        change_type = "AMENDMENT"
        severity = "MEDIUM"

    return {
        "change_type": change_type,
        "severity": severity,
        "summary_text": f"Regulation document detected: {name[:200]}",
        "affected_categories": [],
        "effective_date": None,
    }
