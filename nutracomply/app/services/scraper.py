"""
FSSAI Regulation Scraper (Phase 2)

Monitors:
1. fssai.gov.in regulations page (list of regulation PDFs)
2. FSSAI advisories/directions section
3. egazette.gov.in (Gazette of India, Part III Section 4)

Change detection: SHA-256 hash of each tracked document.
New/changed docs are downloaded, text-extracted, LLM-classified.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings

settings = get_settings()

FSSAI_REGULATIONS_URL = "https://fssai.gov.in/cms/food-safety-and-standards-regulations.php"
FSSAI_ADVISORIES_URL = "https://fssai.gov.in/cms/advisory.php"
AYUSH_ADVISORIES_URL = "https://ayush.gov.in/advisories"
AYUSH_REGULATIONS_URL = "https://ayush.gov.in/regulation-rules-and-acts"
LEGAL_METROLOGY_URL = "https://consumeraffairs.nic.in/policies-rules/legal-metrology-packaged-commodities-rules-2011"
LEGAL_METROLOGY_ACT_URL = "https://consumeraffairs.gov.in/pages/legal-metrology-act"

# Simplified gazette search (FSSAI-related gazette items)
GAZETTE_SEARCH_URL = "https://egazette.gov.in/Search.aspx"

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
    actual regulation/notification/amendment document, and not like a random
    PDF (brochure, form, report, etc.).
    """
    url_lower = url.lower()
    text_lower = (link_text or "").lower().strip()
    combined = url_lower + " " + text_lower

    # Reject known non-regulation patterns first
    if any(pat in combined for pat in _REJECT_PATTERNS):
        return False

    # Accept if either URL path or link text contains regulation keywords
    if any(kw in combined for kw in _REGULATION_KEYWORDS):
        return True

    # If it's a PDF but has no regulation signals at all, reject it
    if ".pdf" in url_lower:
        return False

    # Non-PDF links that passed reject filter but have no positive signal — skip
    return False


def scrape_fssai_pages() -> list[dict]:
    """
    Scrapes FSSAI, AYUSH and Legal Metrology pages.
    Returns list of discovered documents: {url, name, hash, is_new, text_excerpt}
    """
    discovered = []

    discovered += _scrape_regulations_page()
    discovered += _scrape_advisories_page()
    discovered += _scrape_ayush_pages()
    discovered += _scrape_legal_metrology_page()
    discovered += _scrape_egazette_page()

    return discovered


def _scrape_regulations_page() -> list[dict]:
    results = []
    try:
        resp = httpx.get(FSSAI_REGULATIONS_URL, headers=HEADERS, timeout=30, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "lxml")

        # Find regulation PDF links (filtered to actual regulation documents)
        for link in soup.find_all("a", href=True):
            href = link["href"]
            name = link.get_text(strip=True) or Path(href).name
            if (".pdf" in href.lower() or "notification" in href.lower()):
                full_url = _resolve_url(href, FSSAI_REGULATIONS_URL)
                if not _is_regulation_document(full_url, name):
                    continue
                results.append({
                    "source_url": full_url,
                    "document_name": name[:400],
                    "section": "regulations"
                })
    except Exception as e:
        print(f"[scraper] Regulations page error: {e}")

    return results[:50]  # cap to avoid overwhelming


def _scrape_advisories_page() -> list[dict]:
    results = []
    try:
        resp = httpx.get(FSSAI_ADVISORIES_URL, headers=HEADERS, timeout=30, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "lxml")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            name = link.get_text(strip=True) or Path(href).name
            if ".pdf" in href.lower():
                full_url = _resolve_url(href, FSSAI_ADVISORIES_URL)
                if not _is_regulation_document(full_url, name):
                    continue
                results.append({
                    "source_url": full_url,
                    "document_name": name[:400],
                    "section": "advisory"
                })
    except Exception as e:
        print(f"[scraper] Advisories page error: {e}")

    return results[:30]


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
                            "section": "ayush"
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
                            "section": "legal_metrology"
                        })
        except Exception as e:
            print(f"[scraper] Legal Metrology page error ({url}): {e}")
    return results[:20]


def _scrape_egazette_page() -> list[dict]:
    """Scrape eGazette for FSSAI/AYUSH-related gazette notifications (Part III, Section 4)."""
    results = []
    try:
        # Search eGazette for recent FSSAI-related notifications
        # The eGazette site uses POST-based search; we search for FSSAI keywords
        resp = httpx.get(
            "https://egazette.gov.in/Search.aspx",
            headers=HEADERS,
            timeout=30,
            follow_redirects=True,
        )
        soup = BeautifulSoup(resp.text, "lxml")

        # Look for links containing food safety, FSSAI, health supplement keywords
        fssai_keywords = ["fssai", "food safety", "health supplement", "nutraceutical",
                          "labelling", "food additive", "packaged commodity", "ayush"]
        for link in soup.find_all("a", href=True):
            href = link["href"]
            name = link.get_text(strip=True) or ""
            combined = (name + " " + href).lower()
            if any(kw in combined for kw in fssai_keywords):
                full_url = _resolve_url(href, "https://egazette.gov.in/")
                if name and len(name) > 5:
                    results.append({
                        "source_url": full_url,
                        "document_name": f"eGazette: {name[:400]}",
                        "section": "egazette"
                    })
    except Exception as e:
        print(f"[scraper] eGazette page error: {e}")
    return results[:15]


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

        # Extract text
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
            for page in pdf.pages[:5]:  # first 5 pages
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n".join(pages)[:5000]
    except Exception as e:
        print(f"[scraper] PDF text extraction failed: {e}")
        return ""


def classify_regulation_change(document_name: str, text_excerpt: str) -> dict:
    """
    Uses Gemini (or fallback keywords) to classify the type and severity of a change.
    Returns dict with change_type, severity, summary_text, affected_rule_codes.
    """
    if settings.gemini_api_key:
        try:
            return _classify_with_gemini(document_name, text_excerpt)
        except Exception as e:
            print(f"[scraper] Gemini classification failed: {e}")

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
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = CLASSIFICATION_PROMPT.format(name=name, text=text[:3000])
    response = model.generate_content(prompt, generation_config={"temperature": 0.1})
    raw = re.sub(r"^```(?:json)?\s*", "", response.text.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def suggest_rule_modifications(document_name: str, text_excerpt: str, existing_rules: list[dict]) -> list[dict]:
    """
    When a CRITICAL regulation change is detected, use LLM to suggest
    rule modifications or new rules that should be added to the compliance engine.
    Returns list of suggested rule changes: [{action, rule_code, field, old_value, new_value, reason}]
    """
    if not settings.gemini_api_key:
        return []

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

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
            '"field": "field to change (e.g. description, check_config, severity)", '
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
