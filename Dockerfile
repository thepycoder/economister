FROM python:3.13-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gnupg \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor -o /usr/share/keyrings/google-linux.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HEADLESS=true \
    ECONOMISTER_NONINTERACTIVE=true \
    BELGIUM_SECTION=true \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Selenium Manager downloads a matching ChromeDriver; fail the build if Chrome
# cannot start headlessly. Keep this before COPY src so app edits do not
# re-download ChromeDriver.
RUN python -c "from selenium import webdriver; \
opts = webdriver.ChromeOptions(); \
opts.add_argument('--headless=new'); \
opts.add_argument('--no-sandbox'); \
opts.add_argument('--disable-dev-shm-usage'); \
opts.add_argument('--disable-gpu'); \
driver = webdriver.Chrome(options=opts); \
print('Chrome', driver.capabilities.get('browserVersion')); \
driver.quit()"

COPY src ./src

CMD ["python", "src/main.py"]
