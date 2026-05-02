"""
FSSAI Regulation Scraper

Monitors:
1. FSSAI — two pages only:
   - https://fssai.gov.in/cms/food-safety-and-standards-regulations.php
   - https://fssai.gov.in/notifications.php?notification=gazette-notification
2. AYUSH — Ministry of AYUSH advisories and regulation pages
3. Legal Metrology — Department of Consumer Affairs packaged commodities rules

Change detection: SHA-256 hash of each tracked document.
New/changed docs are downloaded, text-extracted, and LLM-classified.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

settings = get_settings()

FSSAI_REGULATIONS_URL = "https://fssai.gov.in/cms/food-safety-and-standards-regulations.php"
FSSAI_GAZETTE_URL     = "https://fssai.gov.in/notifications.php?notification=gazette-notification"
AYUSH_ADVISORIES_URL  = "https://ayush.gov.in/advisories"
AYUSH_REGULATIONS_URL = "https://ayush.gov.in/regulation-rules-and-acts"
LEGAL_METROLOGY_URL   = "https://consumeraffairs.nic.in/policies-rules/legal-metrology-packaged-commodities-rules-2011"
LEGAL_METROLOGY_ACT_URL = "https://consumeraffairs.gov.in/pages/legal-metrology-act"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Keywords that indicate a link points to an actual regulation document
_REGULATION_KEYWORDS = [
    "regulation", "amendment", "notification", "gazette", "order",
    "act", "rule", "standard", "advisory", "direction", "guideline",
    "labelling", "packaged commodit", "food safety", "nutraceutical",
    "health supplement", "ayurved", "prohibition", "restriction",
    "schedule", "annex", "draft", "final", "notifi",
]

# Patterns that indicate non-regulation content to reject
_REJECT_PATTERNS = [
    "brochure", "application form", "application format", "recruitment",
    "tender", "vacancy", "career", "manual", "training",
    "annual report", "annual-report", "newsletter", "magazine",
    "photo", "gallery", "logo", "banner", "infographic",
    "rti", "right to information", "grievance", "feedback form",
    "login", "register", "signup", "download app",
    "organisat", "organigram", "staff list", "telephone directory",
    "visitor", "contact us", "sitemap", "faq",
    "empanelment", "vendor", "quotation", "e-tender",
    "citizen charter", "citizen-charter",
]


def _is_regulation_document(url: str, link_text: str) -> bool:
    """
    Filter helper: returns True only if the URL + link text look like an
    actual regulation/notification/amendment document.
    """
    url_lower = url.lower()
    text_lower = (link_text or "").lower().strip()
    combined = url_lower + " " + text_lower

    if any(pat in combined for pat in _REJECT_PATTERNS):
        return False

    if any(kw in combined for kw in _REGULATION_KEYWORDS):
        return True

    if ".pdf" in url_lower:
        return False

    return False


def scrape_fssai_pages() -> list[dict]:
    """
    Scrapes FSSAI (2 URLs), AYUSH, and Legal Metrology pages.
    Returns list of discovered documents: {source_url, document_name, section}
    """
    discovered = []
    discovered += _scrape_regulations_page()
    discovered += _scrape_gazette_page()
    discovered += _scrape_ayush_pages()
    discovered += _scrape_legal_metrology_page()
    return discovered


def _scrape_regulations_page() -> list[dict]:
    """Scrape FSSAI Food Safety & Standards Regulations page."""
    results = []
    try:
        resp = httpx.get(FSSAI_REGULATIONS_URL, headers=HEADERS, timeout=30, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "lxml")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            name = link.get_text(strip=True) or Path(href).name
            if ".pdf" in href.lower() or "notification" in href.lower():
                full_url = _resolve_url(href, FSSAI_REGULATIONS_URL)
                if not _is_regulation_document(full_url, name):
                    continue
                results.append({
                    "source_url": full_url,
                    "document_name": name[:400],
                    "section": "regulations",
                })
    except Exception as e:
        print(f"[scraper] Regulations page error: {e}")

    return results[:100]


def _scrape_gazette_page() -> list[dict]:
    """Scrape FSSAI Gazette Notifications page."""
    results = []
    try:
        resp = httpx.get(FSSAI_GAZETTE_URL, headers=HEADERS, timeout=30, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "lxml")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            name = link.get_text(strip=True) or Path(href).name
            if not name or len(name) < 3:
                continue
            if ".pdf" in href.lower() or any(
                kw in href.lower() for kw in ["notification", "gazette", "regulation"]
            ):
                full_url = _resolve_url(href, FSSAI_GAZETTE_URL)
                if not _is_regulation_document(full_url, name):
                    continue
                results.append({
                    "source_url": full_url,
                    "document_name": name[:400],
                    "section": "gazette_notification",
                })
    except Exception as e:
        print(f"[scraper] Gazette notifications page error: {e}")

    return results[:100]


def _scrape_ayush_pages() -> list[dict]:
    """Scrape Ministry of AYUSH advisories and regulation pages."""
    results = []
    for url in [AYUSH_ADVISORIES_URL, AYUSH_REGULATIONS_URL]:
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
            soup = BeautifulSoup(resp.text, "lxml")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                name = link.get_text(strip=True) or Path(href).name
                if ".pdf" in href.lower() or any(kw in href.lower() for kw in
                        ["advisory", "notification", "circular", "regulation", "guideline"]):
                    full_url = _resolve_url(href, url)
                    if not _is_regulation_document(full_url, name):
                        continue
                    if name and len(name) > 5:
                        results.append({
                            "source_url": full_url,
                            "document_name": name[:400],
                            "section": "ayush",
                        })
        except Exception as e:
            print(f"[scraper] AYUSH page error ({url}): {e}")
    return results[:25]


def _scrape_legal_metrology_page() -> list[dict]:
    """Scrape Department of Consumer Affairs — Legal Metrology packaged commodities rules."""
    results = []
    for url in [LEGAL_METROLOGY_URL, LEGAL_METROLOGY_ACT_URL]:
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
            soup = BeautifulSoup(resp.text, "lxml")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                name = link.get_text(strip=True) or Path(href).name
                if ".pdf" in href.lower() or any(kw in href.lower() for kw in
                        ["amendment", "rule", "notification", "circular", "packaged"]):
                    full_url = _resolve_url(href, url)
                    if not _is_regulation_document(full_url, name):
                        continue
                    if name and len(name) > 5:
                        results.append({
                            "source_url": full_url,
                            "document_name": name[:400],
                            "section": "legal_metrology",
                        })
        except Exception as e:
            print(f"[scraper] Legal Metrology page error ({url}): {e}")
    return results[:20]


def _resolve_url(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return base_url.rsplit("/", 1)[0] + "/" + href


def download_and_hash(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Downloads a PDF/page, returns (text_content, sha256_hash).
    Returns (None, None) on failure.
    """
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        content = resp.content
        sha256 = hashlib.sha256(content).hexdigest()

        if url.lower().endswith(".pdf") or "application/pdf" in resp.headers.get("content-type", ""):
            text = _extract_pdf_text_from_bytes(content)
        else:
            soup = BeautifulSoup(content, "lxml")
            text = soup.get_text(separator="\n", strip=True)[:5000]

        return text, sha256
    except Exception as e:
        print(f"[scraper] Download failed {url}: {e}")
        return None, None


def _extract_pdf_text_from_bytes(content: bytes) -> str:
    try:
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = []
            for page in pdf.pages[:5]:  # first 5 pages only
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n".join(pages)[:5000]
    except Exception as e:
        print(f"[scraper] PDF text extraction failed: {e}")
        return ""


def classify_regulation_change(document_name: str, text_excerpt: str) -> dict:
    """
    Uses Claude Haiku to classify the type and severity of a regulation change.
    Falls back to keyword heuristics if Claude is unavailable.
    """
    if settings.anthropic_api_key:
        try:
            return _classify_with_claude(document_name, text_excerpt)
        except Exception as e:
            print(f"[scraper] Claude classification failed: {e}")

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


def _classify_with_claude(name: str, text: str) -> dict:
    import anthropic as _anthropic
    _client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = CLASSIFICATION_PROMPT.format(name=name, text=text[:3000])
    response = _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = re.sub(r"^```(?:json)?\s*", "", response.content[0].text.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def suggest_rule_modifications(document_name: str, text_excerpt: str, existing_rules: list[dict]) -> list[dict]:
    """
    When a CRITICAL regulation change is detected, use Claude Haiku to suggest
    rule modifications or new rules that should be added to the compliance engine.
    Returns list of suggested rule changes.
    """
    if not settings.anthropic_api_key:
        return []

    try:
        import anthropic as _anthropic
        _suggest_client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)

        rules_summary = "\n".join(
            f"- {r['rule_code']}: {r['description'][:100]}" for r in existing_rules[:30]
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

        response = _suggest_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = re.sub(r"^```(?:json)?\s*", "", response.content[0].text.strip())
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        print(f"[scraper] Rule modification suggestion failed: {e}")
        return []


def _classify_with_keywords(name: str, text: str) -> dict:
    combined = (name + " " + text).lower()

    change_type = "UNKNOWN"
    severity = "MEDIUM"

    if any(w in combined for w in ["ban", "prohibited", "not permitted", "remove from"]):
        change_type = "INGREDIENT_BAN"
        severity = "CRITICAL"
    elif any(w in combined for w in ["restrict", "limit", "maximum daily", "dosage limit"]):
        change_type = "INGREDIENT_RESTRICTION"
        severity = "HIGH"
    elif any(w in combined for w in ["label", "labelling", "declaration", "marking", "font"]):
        change_type = "LABEL_REQUIREMENT"
        severity = "HIGH"
    elif any(w in combined for w in ["health claim", "claim", "structure function"]):
        change_type = "HEALTH_CLAIM"
        severity = "MEDIUM"
    elif any(w in combined for w in ["new regulation", "notified", "gazette"]):
        change_type = "NEW_REGULATION"
        severity = "HIGH"
    elif any(w in combined for w in ["amend", "amendment", "revised", "updated"]):
        change_type = "AMENDMENT"
        severity = "MEDIUM"

    return {
        "change_type": change_type,
        "severity": severity,
        "summary_text": f"Regulation document detected: {name[:200]}",
        "affected_categories": [],
        "effective_date": None,
    }
