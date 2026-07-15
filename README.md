# 📰 Economister

*Transform The Economist weekly edition into EPUB files for offline reading on any e-reader.* **⚠️ Requires an active Economist subscription**

## ✨ Features

- 📚 **Complete Weekly Edition** - All 50+ articles from the current issue
- 🗂️ **Hierarchical Table of Contents** - Organized by sections (Leaders, Business, Science, etc.)
- 🖼️ **Full Image Support** - High-resolution images, charts, and the magazine cover
- 📖 **Professional Formatting** - Preserves italics, bold text, blockquotes, and typography
- 🎨 **Economist Styling** - Matches the magazine's classic design and readability
- 📱 **Universal Compatibility** - Works on Kindle, Kobo, iPad, and all EPUB readers
- 🔍 **Smart Content Extraction** - Filters out ads, navigation, and duplicate content
- 📊 **Detailed Metadata** - Publication date, article count, and reading statistics

![EPUB Preview](doc/epub.png)

## 🚀 How It Works

Economister opens Chrome, logs in to The Economist, then downloads and converts the entire weekly edition. With credentials in a `.env` file, login is fully automated; otherwise you log in manually in the browser.

1. **Chrome Opens** → A Chrome browser window appears
2. **Login** → Automated from `.env`, or manual (handle any CAPTCHAs/2FA)
3. **Tool Takes Over** → Downloads all articles and creates EPUB
4. **EPUB Ready** → Find your file in `ebooks/economist_YYYY-MM-DD.epub`

## Prerequisites

- **Python 3.11–3.13** (3.14 is not supported yet — `lxml` / `ebooklib` need wheels)
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **Google Chrome Browser** (must be installed — Selenium controls it but does not install it)
- **Active Economist Subscription**

## Quick Start

```bash
# 1. Clone and enter directory
git clone https://github.com/yourusername/economister.git
cd economister

# 2. Install dependencies (creates .venv with Python 3.13)
uv sync

# 3. Configure login credentials (recommended)
cp .env.example .env
# Edit .env and set ECONOMIST_EMAIL and ECONOMIST_PASSWORD

# 4. Install ChromeDriver (required for Selenium)
# macOS:
brew install chromedriver

# Ubuntu/Debian:
sudo apt-get install chromium-chromedriver

# Windows:
# Download from https://chromedriver.chromium.org
# Add to PATH or place in project directory

# 5. Run the tool
uv run python src/main.py
```

### `.env` credentials

Copy `.env.example` to `.env` in the project root (`.env` is gitignored):

```bash
cp .env.example .env
```

Set your Economist subscription email and password:

```env
ECONOMIST_EMAIL=your-email@example.com
ECONOMIST_PASSWORD=your-password
```

When both variables are set, `main.py` and `scripts/audit_wtw.py` log in automatically. If automation fails (CAPTCHA, 2FA, etc.), the tool falls back to manual login in the browser.

Without a `.env` file, run as before: log in manually when prompted and press Enter to continue.

## Project Structure

```
src/
├── main.py              # Main entry point
├── config.py            # Configuration and constants
├── models.py            # Data models (Article, Edition, etc.)
├── browser.py           # Browser management with Selenium
├── content_extractor.py # HTML parsing and content extraction
├── scraper.py           # Main scraping orchestrator
├── epub_builder.py      # EPUB file generation
├── image_handler.py     # Image downloading and processing
└── utils.py             # Utility functions
```

# Input/Output

```bash
# Download current weekly edition (50+ articles)
uv run python src/main.py

# Quick test with 5 articles from current edition
uv run python src/main.py --limit 5

# Debug mode (saves HTML files)
uv run python src/main.py --debug

# Run tests
uv run python src/test.py

# Audit "The world this week" coverage (auto-login when .env is configured)
uv run python scripts/audit_wtw.py --fetch-articles
uv run python scripts/audit_wtw.py --login --fetch-articles  # manual login fallback
```

**Note**: All commands download from the current weekly edition only. There is no option to specify past editions.

Example output from running this would be:

```txt
============================================================
✅ EPUB CREATED SUCCESSFULLY!
============================================================
📖 Edition: The Economist - August 16, 2025
📚 Articles: 62
📑 Sections: 16
📄 Est. Pages: ~310
🖼️  Images: 92
💾 File Size: 21.66 MB
📁 Location: ebooks/economist_2025-08-16.epub
============================================================
```


## Troubleshooting

### ChromeDriver Issues
```bash
# Check Chrome version
google-chrome --version  # or chrome --version

# Download matching ChromeDriver version from:
# https://chromedriver.chromium.org/downloads
```

### Login Problems
- Add `ECONOMIST_EMAIL` and `ECONOMIST_PASSWORD` to `.env` for automated login
- Complete any CAPTCHAs that appear during manual fallback
- Handle 2FA if enabled
- Wait for the page to fully load before pressing Enter (manual mode)
- Don't close the browser window

### Missing Articles
- Some special reports may require different selectors
- Run with `--debug` to analyze HTML
- Check `debug/` folder for saved pages

## Login

The Economist uses bot detection (CAPTCHAs, behavior analysis, browser fingerprinting). **Recommended:** put credentials in `.env` for automated login via the Salesforce account page.

If automation is blocked or you use 2FA, the tool falls back to manual login in Chrome — you complete authentication in the browser, then press Enter to continue.

## Legal

This tool requires a valid Economist subscription. It only formats content you already have access to for e-reader compatibility. The tool is strictly limited to the current weekly edition to ensure responsible use. See [doc/legal.md](doc/legal.md) for detailed legal analysis of format shifting rights with valid subscriptions.

## Contributing

See [doc/learnings.md](doc/learnings.md) for the complete development journey, including why we use manual login and how we solved various technical challenges.

**This tool is intentionally limited to downloading ONLY the current weekly edition.** The ability to target specific past editions or date ranges is not permitted and will not be implemented. This limitation ensures the tool:
- Respects The Economist's content distribution model
- Cannot be used to scrape their entire article library
- Remains focused on its intended purpose: format-shifting the current issue for e-reader compatibility

Other than that any contributions or modifications are allowed, so long as they adhere to:

- **Testing**: Run `uv run python src/test.py` before submitting PRs
- **Code Style**: Follow Google Python Style Guide
- **Security**: Never commit credentials or bypass authentication


---

*For readers who value their time, their sources of information, and especially The Economist.*
