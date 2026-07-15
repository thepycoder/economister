#!/usr/bin/env python3
"""Temporary audit: compare live weekly edition vs scraper link extraction.

Usage:
  uv run python scripts/audit_wtw.py              # headless, no login (may be blocked)
  uv run python scripts/audit_wtw.py --login      # manual login via Enter
  uv run python scripts/audit_wtw.py              # auto-login when .env has credentials
  uv run python scripts/audit_wtw.py --html FILE  # offline analysis of saved HTML
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

# Repo src imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bs4 import BeautifulSoup  # noqa: E402
from browser import dismiss_cookie_banner, login_automated  # noqa: E402
from content_extractor import ContentExtractor  # noqa: E402
from config import (  # noqa: E402
    ECONOMIST_EMAIL,
    ECONOMIST_PASSWORD,
    ECONOMIST_URL,
    LOGIN_URL,
    PAGE_LOAD_WAIT_TIME,
)
from utils import (  # noqa: E402
    detect_section_from_url,
    has_extractable_content,
    is_valid_article_url,
)


WTW_SELECTOR = "div.layout-weekly-edition-wtw"
SECTION_SELECTOR = "div.layout-weekly-edition-section"


def extract_wtw_block_links(html: str) -> list[dict[str, str]]:
    """Links from dedicated WTW container (Economist2Epub approach)."""
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one(WTW_SELECTOR)
    if not block:
        return []

    links = []
    for a in block.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(" ", strip=True)
        if not href:
            continue
        if not href.startswith("http"):
            href = urljoin("https://www.economist.com", href)
        links.append({"title": text, "url": href, "source": "wtw_block"})
    return links


def extract_section_block_links(html: str) -> list[dict[str, str]]:
    """All links inside weekly-edition section containers."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen: set[str] = set()
    for block in soup.select(SECTION_SELECTOR):
        for a in block.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(" ", strip=True)
            if not href:
                continue
            if not href.startswith("http"):
                href = urljoin("https://www.economist.com", href)
            if href in seen:
                continue
            seen.add(href)
            links.append({"title": text, "url": href, "source": "section_block"})
    return links


def extract_all_article_hrefs(html: str) -> list[dict[str, str]]:
    """Every economist article-shaped href on the page (no text filter)."""
    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(r"/202[4-9]/\d{2}/\d{2}/")
    links = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(" ", strip=True)
        if not pattern.search(href):
            continue
        if not href.startswith("http"):
            href = urljoin("https://www.economist.com", href)
        if href in seen:
            continue
        seen.add(href)
        links.append({
            "title": text,
            "url": href,
            "section": detect_section_from_url(href),
            "text_len": len(text),
            "passes_scraper_filter": is_valid_article_url(href, text),
        })
    return links


def analyze_weekly_edition(html: str) -> dict[str, Any]:
    """Compare discovery methods on weekly edition HTML."""
    extractor = ContentExtractor()
    scraper_links = extractor.extract_article_links(html)
    scraper_urls = {x["url"] for x in scraper_links}

    wtw_block = extract_wtw_block_links(html)
    wtw_urls = {x["url"] for x in wtw_block}

    all_hrefs = extract_all_article_hrefs(html)
    all_urls = {x["url"] for x in all_hrefs}

    wtw_on_page = [x for x in all_hrefs if "/the-world-this-week/" in x["url"]]
    wtw_filtered_out = [
        x for x in wtw_on_page if not x["passes_scraper_filter"]
    ]

    return {
        "wtw_block_present": bool(BeautifulSoup(html, "html.parser").select_one(WTW_SELECTOR)),
        "wtw_block_links": wtw_block,
        "scraper_link_count": len(scraper_links),
        "scraper_wtw_count": sum(
            1 for x in scraper_links if x["section"] == "The world this week"
        ),
        "all_article_href_count": len(all_hrefs),
        "wtw_on_page": wtw_on_page,
        "wtw_filtered_out_by_is_valid_article_url": wtw_filtered_out,
        "wtw_in_scraper": [x for x in wtw_on_page if x["url"] in scraper_urls],
        "wtw_missing_from_scraper": [
            x for x in wtw_on_page if x["url"] not in scraper_urls
        ],
        "on_page_not_in_scraper": [
            x for x in all_hrefs
            if x["url"] not in scraper_urls and x["passes_scraper_filter"]
        ],
        "section_block_link_count": len(extract_section_block_links(html)),
        "scraper_section_counts": _section_counts(scraper_links),
        "page_section_counts": _section_counts(
            [{"section": x["section"], "url": x["url"]} for x in all_hrefs]
        ),
    }


def _section_counts(links: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for link in links:
        sec = link.get("section") or "Other"
        counts[sec] = counts.get(sec, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def detect_block(html: str, final_url: str | None = None) -> tuple[bool, str | None]:
    """Return (blocked, reason). Only true blocks should skip article fetches."""
    lower = html.lower()
    cf_challenge = (
        "just a moment" in lower
        or "challenge-platform" in lower
        or "cf-turnstile" in lower
        or "performing security verification" in lower
    )
    if cf_challenge:
        return True, "cloudflare_turnstile_challenge"

    has_weekly_content = (
        "/the-world-this-week/" in html
        or "/weeklyedition/" in lower
        or (final_url and "weeklyedition" in final_url)
    )
    if has_weekly_content and len(html) >= 15000:
        legacy_markup_missing = "layout-weekly-edition" not in html
        if legacy_markup_missing:
            return False, "legacy_layout_markup_absent"
        return False, None

    if len(html) < 15000:
        return True, f"page_too_short_or_no_edition_markup (len={len(html)})"

    return True, "no_weekly_edition_content_detected"


def create_chrome_driver(*, headless: bool):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.binary_location = "/usr/bin/chromium"
    if headless:
        options.add_argument("--headless=new")

    return webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)


def has_env_credentials() -> bool:
    """Return True when .env provides Economist login credentials."""
    return bool(ECONOMIST_EMAIL and ECONOMIST_PASSWORD)


def prompt_manual_login(driver) -> None:
    """Open login page and wait for the user to authenticate."""
    print(f"Opening login: {LOGIN_URL}")
    driver.get(LOGIN_URL)
    dismiss_cookie_banner(driver, timeout=3)
    print("\n" + "=" * 60)
    print("Log in in the browser window, then press Enter here.")
    print("=" * 60)
    input()
    dismiss_cookie_banner(driver, timeout=3)


def authenticate_driver(driver, *, allow_manual: bool) -> tuple[bool, str]:
    """Try auto-login from .env, optionally fall back to manual login."""
    if has_env_credentials():
        print("Attempting automated login from .env credentials...")
        if login_automated(driver, ECONOMIST_EMAIL, ECONOMIST_PASSWORD):
            return True, "auto_login"
        print("Automated login failed.", file=sys.stderr)

    if allow_manual:
        prompt_manual_login(driver)
        return True, "login"

    return False, "headless"


def analyze_article_content(html: str, url: str) -> dict[str, Any]:
    """Simulate scraper article extraction and validation."""
    extractor = ContentExtractor()
    article = extractor.extract_article(html, url)
    p_tags = BeautifulSoup(html, "html.parser").find_all("p")
    list_items = BeautifulSoup(html, "html.parser").find_all("li")
    data_paragraphs = BeautifulSoup(html, "html.parser").find_all(
        "p", attrs={"data-component": "paragraph"}
    )

    return {
        "url": url,
        "title": article.title,
        "paragraph_count": article.paragraph_count,
        "image_count": article.image_count,
        "would_pass_content_check": has_extractable_content(article),
        "raw_p_tag_count": len(p_tags),
        "raw_li_count": len(list_items),
        "data_component_paragraph_count": len(data_paragraphs),
    }


def wtw_urls_from_report(weekly_edition: dict[str, Any]) -> list[str]:
    """WTW article URLs to fetch — prefer dedicated block, fall back to page scan."""
    urls = [x["url"] for x in weekly_edition.get("wtw_block_links", [])]
    if not urls:
        urls = [x["url"] for x in weekly_edition.get("wtw_on_page", [])]
    return urls


def fetch_wtw_articles(driver, urls: list[str]) -> list[dict[str, Any]]:
    """Fetch and analyze WTW article pages using an existing browser session."""
    results = []
    for url in urls[:5]:
        print(f"Fetching article: {url}")
        driver.get(url)
        time.sleep(PAGE_LOAD_WAIT_TIME)
        dump_name = url.rstrip("/").split("/")[-1] + ".html"
        dump_path = ROOT / "debug" / f"wtw_article_{dump_name}"
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(driver.page_source, encoding="utf-8")
        result = analyze_article_content(driver.page_source, url)
        result["html_dump"] = str(dump_path)
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit WTW vs scraper")
    parser.add_argument("--login", action="store_true", help="Manual login flow")
    parser.add_argument("--html", type=Path, help="Analyze saved HTML file")
    parser.add_argument(
        "--fetch-articles",
        action="store_true",
        help="Fetch WTW article pages (needs --login or working session)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "debug" / "wtw_audit_report.json",
        help="JSON report path",
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "audit_mode": "html_file" if args.html else "headless",
        "login_completed": False,
        "blocked": False,
        "block_reason": None,
        "warning": None,
        "final_url": None,
    }

    has_creds = has_env_credentials()
    wants_login = args.login or has_creds

    driver = None
    try:
        if args.html:
            html = args.html.read_text(encoding="utf-8")
            report["final_url"] = str(args.html)
            blocked, reason = detect_block(html, report["final_url"])
            report["blocked"] = blocked
            if blocked:
                report["block_reason"] = reason
            elif reason:
                report["warning"] = reason
        else:
            try:
                driver = create_chrome_driver(headless=not wants_login)
                if wants_login:
                    logged_in, mode = authenticate_driver(
                        driver, allow_manual=args.login or not has_creds
                    )
                    report["audit_mode"] = mode
                    report["login_completed"] = logged_in
                    if not logged_in:
                        report["blocked"] = True
                        report["block_reason"] = "login_required"
                        args.out.write_text(
                            json.dumps(report, indent=2), encoding="utf-8"
                        )
                        print(json.dumps(report, indent=2))
                        return 1

                print(f"Navigating: {ECONOMIST_URL}")
                driver.get(ECONOMIST_URL)
                dismiss_cookie_banner(driver, timeout=3)
                time.sleep(PAGE_LOAD_WAIT_TIME)
                html = driver.page_source
                report["final_url"] = driver.current_url
            except Exception as e:
                report["blocked"] = True
                report["block_reason"] = f"browser_error: {e}"
                args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(json.dumps(report, indent=2))
                return 1

            blocked, reason = detect_block(html, report["final_url"])
            report["blocked"] = blocked
            if blocked:
                report["block_reason"] = reason
            elif reason:
                report["warning"] = reason

            dump = args.out.parent / "wtw_audit_weekly_edition.html"
            dump.write_text(html, encoding="utf-8")
            report["html_dump"] = str(dump)

        report["weekly_edition"] = analyze_weekly_edition(html)
        wtw_urls = wtw_urls_from_report(report["weekly_edition"])

        if args.fetch_articles:
            if report["blocked"]:
                print(
                    "Skipping --fetch-articles: edition page blocked "
                    f"({report['block_reason']})",
                    file=sys.stderr,
                )
            elif not wtw_urls:
                print("Skipping --fetch-articles: no WTW URLs found", file=sys.stderr)
            elif args.html:
                if not wants_login:
                    print(
                        "Skipping --fetch-articles: use --login or .env "
                        "credentials to fetch article pages in a browser session",
                        file=sys.stderr,
                    )
                else:
                    driver = create_chrome_driver(headless=False)
                    logged_in, mode = authenticate_driver(
                        driver, allow_manual=args.login or not has_creds
                    )
                    report["audit_mode"] = mode
                    report["login_completed"] = logged_in
                    if logged_in:
                        report["wtw_article_content"] = fetch_wtw_articles(
                            driver, wtw_urls
                        )
            else:
                report["wtw_article_content"] = fetch_wtw_articles(driver, wtw_urls)
    finally:
        if driver:
            driver.quit()

    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if report["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
