"""Browser management for web scraping."""

import atexit
import time
from typing import List, Optional

import requests
from requests.cookies import create_cookie
from selenium import webdriver
from selenium.common.exceptions import (
  ElementClickInterceptedException,
  TimeoutException,
  WebDriverException,
)
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import (
  ECONOMIST_EMAIL,
  ECONOMIST_PASSWORD,
  HEADLESS,
  LOGIN_URL,
  NONINTERACTIVE,
  PAGE_LOAD_WAIT_TIME,
  USER_AGENT,
)

COOKIE_BANNER_SELECTORS = [
  "#onetrust-accept-btn-handler",
  "button#onetrust-accept-btn-handler",
  "#accept-recommended-btn-handler",
  ".onetrust-close-btn-handler",
  "button[aria-label='Accept cookies']",
  "button[aria-label='Accept all cookies']",
  "button[title='Accept Cookies']",
]

CONSENT_IFRAME_SELECTORS = [
  "iframe[src*='consent.economist.com']",
  "iframe[id^='sp_message_iframe']",
  "iframe[title*='Privacy and Consent']",
]

CONSENT_ACCEPT_CSS_SELECTORS = [
  "button.sp_choice_type_11",
  "button[title='Accept all']",
  "button[aria-label='Accept all']",
]

CONSENT_ACCEPT_XPATH_SELECTORS = [
  "//button[normalize-space()='Accept all']",
]

# Salesforce Community login (myaccount.economist.com) uses LWC inputs.
EMAIL_CSS_SELECTORS = [
  "input[name='username']",
  "input[inputmode='email']",
  "input.slds-input[inputmode='email']",
  "input[type='email']",
  "input#username",
  "input[autocomplete='username']",
]

EMAIL_XPATH_SELECTORS = [
  "//input[@name='username']",
  "//label[contains(.,'Email')]/..//input",
]

PASSWORD_CSS_SELECTORS = [
  "input[name='password']",
  "input[type='password']",
  "input#password",
  "input[autocomplete='current-password']",
]

PASSWORD_XPATH_SELECTORS = [
  "//input[@name='password']",
  "//label[contains(.,'Password')]/..//input",
]

SUBMIT_CSS_SELECTORS = [
  "button.slds-button_brand[type='submit']",
  "button[type='submit']",
  "input[type='submit']",
  "button.login-button",
  "button[name='Login']",
]

SUBMIT_XPATH_SELECTORS = [
  "//button[@type='submit' and contains(.,'Log in')]",
  "//button[normalize-space()='Log in']",
]


def _safe_current_url(driver: WebDriver) -> str:
  """Return current URL, or empty string if the browser tab is gone."""
  try:
    return driver.current_url
  except WebDriverException:
    return ""


def _safe_navigate(driver: WebDriver, url: str) -> bool:
  """Navigate to URL; return False if the tab or session died."""
  try:
    driver.get(url)
    _ = driver.current_url
    return True
  except WebDriverException:
    return False


def _wait_for_page_ready(driver: WebDriver, timeout: int = 30) -> bool:
  """Wait until document.readyState is complete."""
  try:
    WebDriverWait(driver, timeout).until(
      lambda d: d.execute_script("return document.readyState")
      == "complete"
    )
    return True
  except (TimeoutException, WebDriverException):
    return False


def _is_still_authenticating(url: str) -> bool:
  """Return True while the browser is still in the login/OAuth flow."""
  url = url.lower()
  if "/api/auth/login" in url:
    return True
  if "myaccount.economist.com/s/login" in url:
    return True
  if "remoteaccessauthorizationpage" in url:
    return True
  if "myaccount.economist.com/setup/secur" in url:
    return True
  return False


def _wait_for_login_complete(driver: WebDriver, timeout: int = 60) -> bool:
  """Wait for Salesforce OAuth to finish on economist.com."""
  print("Waiting for login redirect...")
  try:
    WebDriverWait(driver, timeout).until(
      lambda d: (
        not _is_still_authenticating(_safe_current_url(d))
        and "economist.com" in _safe_current_url(d).lower()
      )
    )
    _wait_for_page_ready(driver, timeout=30)
    time.sleep(1)
    return True
  except TimeoutException:
    url = _safe_current_url(driver).lower()
    if _is_still_authenticating(url):
      return False
    return "economist.com" in url
  except WebDriverException:
    return False


def _find_element(
  driver: WebDriver,
  css_selectors: List[str],
  xpath_selectors: Optional[List[str]] = None,
  timeout: int = 20,
):
  """Return the first element matching any CSS or XPath selector."""
  deadline = time.time() + timeout
  while time.time() < deadline:
    for selector in css_selectors:
      for element in driver.find_elements(By.CSS_SELECTOR, selector):
        if element.is_displayed():
          return element
    for xpath in xpath_selectors or []:
      for element in driver.find_elements(By.XPATH, xpath):
        if element.is_displayed():
          return element
    time.sleep(0.25)
  raise TimeoutException(
    f"No elements found for selectors: {css_selectors + (xpath_selectors or [])}"
  )


def _element_exists(
  driver: WebDriver,
  css_selectors: List[str],
  xpath_selectors: Optional[List[str]] = None,
  timeout: int = 3,
) -> bool:
  """Return True if any selector matches a visible element."""
  try:
    _find_element(
      driver, css_selectors, xpath_selectors, timeout=timeout
    )
    return True
  except TimeoutException:
    return False


def _fill_first(
  driver: WebDriver,
  css_selectors: List[str],
  value: str,
  xpath_selectors: Optional[List[str]] = None,
  timeout: int = 20,
) -> bool:
  """Fill the first matching input field."""
  try:
    field = _find_element(
      driver, css_selectors, xpath_selectors, timeout=timeout
    )
    field.click()
    field.clear()
    field.send_keys(value)
    return True
  except TimeoutException:
    return False


def _click_element(driver: WebDriver, element) -> None:
  """Click an element, falling back to JavaScript if obscured."""
  driver.execute_script(
    "arguments[0].scrollIntoView({block: 'center'});", element
  )
  time.sleep(0.2)
  try:
    element.click()
  except ElementClickInterceptedException:
    driver.execute_script("arguments[0].click();", element)


def _click_first(
  driver: WebDriver,
  css_selectors: List[str],
  xpath_selectors: Optional[List[str]] = None,
  timeout: int = 10,
) -> bool:
  """Click the first matching clickable element."""
  try:
    button = _find_element(
      driver, css_selectors, xpath_selectors, timeout=timeout
    )
    _click_element(driver, button)
    return True
  except TimeoutException:
    return False


def _find_consent_iframe(driver: WebDriver):
  """Return the Sourcepoint consent iframe if present."""
  for selector in CONSENT_IFRAME_SELECTORS:
    for iframe in driver.find_elements(By.CSS_SELECTOR, selector):
      try:
        if iframe.is_displayed():
          return iframe
      except WebDriverException:
        continue
  return None


def _dismiss_onetrust_banner(driver: WebDriver) -> bool:
  """Click a OneTrust accept button on the main page."""
  for selector in COOKIE_BANNER_SELECTORS:
    for button in driver.find_elements(By.CSS_SELECTOR, selector):
      try:
        if button.is_displayed() and button.is_enabled():
          _click_element(driver, button)
          time.sleep(0.5)
          return True
      except WebDriverException:
        continue
  return False


def _dismiss_sourcepoint_consent(driver: WebDriver) -> bool:
  """Accept cookies in the Economist Sourcepoint consent iframe."""
  iframe = _find_consent_iframe(driver)
  if not iframe:
    return False

  try:
    driver.switch_to.frame(iframe)
    button = _find_element(
      driver,
      CONSENT_ACCEPT_CSS_SELECTORS,
      CONSENT_ACCEPT_XPATH_SELECTORS,
      timeout=3,
    )
    _click_element(driver, button)
    time.sleep(0.5)
    return True
  except (TimeoutException, WebDriverException):
    return False
  finally:
    try:
      driver.switch_to.default_content()
    except WebDriverException:
      pass


def dismiss_cookie_banner(
  driver: WebDriver, timeout: int = 2
) -> bool:
  """Try to dismiss Economist cookie/consent banners.

  The site uses a Sourcepoint iframe (consent.economist.com) rather than
  an on-page OneTrust bar. This polls for both.

  Args:
      driver: Active WebDriver instance.
      timeout: Total seconds to poll for a dismiss button.

  Returns:
      True if a banner was dismissed.
  """
  current = _safe_current_url(driver).lower()
  if "myaccount.economist.com" in current:
    # Economist consent UI lives on www.economist.com, not Salesforce login.
    return False

  deadline = time.time() + timeout
  while time.time() < deadline:
    try:
      if _dismiss_onetrust_banner(driver):
        return True
      if _dismiss_sourcepoint_consent(driver):
        return True
    except WebDriverException:
      return False
    time.sleep(0.3)
  return False


def _wait_for_login_page(driver: WebDriver, timeout: int = 30) -> bool:
  """Wait until the Salesforce login form is rendered."""
  try:
    WebDriverWait(driver, timeout).until(
      lambda d: "myaccount.economist.com" in d.current_url
    )
    _find_element(
      driver,
      EMAIL_CSS_SELECTORS,
      EMAIL_XPATH_SELECTORS,
      timeout=timeout,
    )
    return True
  except TimeoutException:
    return False


def _verify_logged_in(driver: WebDriver) -> bool:
  """Confirm the browser finished OAuth and left the login flow."""
  if not _wait_for_login_complete(driver):
    return False

  print("Dismissing cookie banner...")
  dismiss_cookie_banner(driver, timeout=10)

  current = _safe_current_url(driver).lower()
  if _is_still_authenticating(current):
    return False
  if "myaccount.economist.com" in current:
    return False
  if "/api/auth/login" in current:
    return False
  return "economist.com" in current


def login_automated(
  driver: WebDriver, email: str, password: str
) -> bool:
  """Log in via Salesforce redirect using email and password.

  Args:
      driver: Active WebDriver instance.
      email: Economist account email.
      password: Economist account password.

  Returns:
      True if login succeeded and session was verified.
  """
  print("Navigating to login page...")
  if not _safe_navigate(driver, LOGIN_URL):
    return False
  dismiss_cookie_banner(driver, timeout=2)

  print("Waiting for login form...")
  if not _wait_for_login_page(driver):
    print("Timed out waiting for login form")
    return False

  print("Entering email...")
  if not _fill_first(
    driver, EMAIL_CSS_SELECTORS, email, EMAIL_XPATH_SELECTORS
  ):
    print("Could not find email field")
    return False

  print("Entering password...")
  if not _fill_first(
    driver, PASSWORD_CSS_SELECTORS, password, PASSWORD_XPATH_SELECTORS
  ):
    print("Could not find password field")
    return False

  print("Submitting login...")
  if not _click_first(
    driver, SUBMIT_CSS_SELECTORS, SUBMIT_XPATH_SELECTORS
  ):
    print("Could not find login submit button")
    return False

  if _verify_logged_in(driver):
    return True

  print("Login submitted but session verification failed")
  return False


def is_cloudflare_challenge(title: str, html: str) -> bool:
  """Return True when the page is a Cloudflare bot interstitial."""
  lowered_title = str(title or "").strip().lower()
  if lowered_title.startswith("just a moment") or "attention required" in (
    lowered_title
  ):
    return True
  head = str(html or "")[:8000].lower()
  markers = (
    "cdn-cgi/challenge",
    "cf-browser-verification",
    "cf-challenge",
    "checking your browser before accessing",
  )
  return any(marker in head for marker in markers)


def wait_out_cloudflare(driver: WebDriver, timeout: int = 25) -> bool:
  """Wait until a Cloudflare challenge page is replaced by real content.

  Returns:
      True if the challenge cleared (or was never present).
  """
  try:
    WebDriverWait(driver, timeout).until(
      lambda d: not is_cloudflare_challenge(
        getattr(d, "title", "") or "",
        getattr(d, "page_source", "") or "",
      )
    )
    return True
  except TimeoutException:
    print("  Cloudflare challenge did not clear")
    return False


class BrowserManager:
  """Manages browser instance and authentication."""

  def __init__(self):
    """Initialize browser manager."""
    self.driver: Optional[WebDriver] = None
    self._headless = HEADLESS
    atexit.register(self.quit)

  def setup(self, headless: Optional[bool] = None) -> None:
    """Initialize Selenium Chrome driver with anti-detection options.

    Args:
        headless: Override HEADLESS env setting for this launch.

    Raises:
        RuntimeError: If Chrome or ChromeDriver is not installed.
    """
    use_headless = HEADLESS if headless is None else headless
    mode = "headless" if use_headless else "headed"
    print(f"Starting Chrome browser ({mode})...")
    try:
      options = webdriver.ChromeOptions()
      if use_headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
      options.add_argument(f"--user-agent={USER_AGENT}")
      options.add_argument("--disable-blink-features=AutomationControlled")
      options.add_experimental_option("excludeSwitches", ["enable-logging"])
      options.add_experimental_option(
        "prefs",
        {"profile.default_content_setting_values.notifications": 2},
      )
      self.driver = webdriver.Chrome(options=options)
      self._headless = use_headless
    except Exception as e:
      raise RuntimeError(
        f"Failed to start Chrome browser. Ensure Chrome and ChromeDriver "
        f"are installed: {e}"
      )

  def _is_browser_healthy(self) -> bool:
    """Return False if the browser tab has crashed or the session is dead."""
    if not self.driver:
      return False
    try:
      _ = self.driver.current_url
      return True
    except WebDriverException:
      return False

  def _restart_browser(self, headless: Optional[bool] = None) -> None:
    """Restart Chrome after a tab crash or mode switch."""
    mode = "headless" if (HEADLESS if headless is None else headless) else "headed"
    print(f"Restarting browser ({mode})...")
    self.quit()
    self.setup(headless=headless)

  def export_requests_session(self) -> requests.Session:
    """Copy authenticated browser cookies into a requests session."""
    if not self.driver:
      raise RuntimeError("Browser not initialized. Call setup() first.")

    session = requests.Session()
    user_agent = USER_AGENT
    try:
      detected = self.driver.execute_script("return navigator.userAgent")
      if isinstance(detected, str) and detected.strip():
        user_agent = detected.strip()
    except WebDriverException:
      pass
    session.headers.update({"User-Agent": user_agent})
    for cookie in self.driver.get_cookies():
      expires = cookie.get("expiry")
      session.cookies.set_cookie(
        create_cookie(
          name=cookie["name"],
          value=cookie["value"],
          domain=cookie.get("domain"),
          path=cookie.get("path", "/"),
          secure=bool(cookie.get("secure")),
          expires=expires,
          rest={"HttpOnly": cookie.get("httpOnly")},
        )
      )
    return session

  def login(self) -> None:
    """Authenticate via .env credentials or manual browser login."""
    if not self.driver:
      raise RuntimeError("Browser not initialized. Call setup() first.")

    if ECONOMIST_EMAIL and ECONOMIST_PASSWORD:
      print("Attempting automated login from .env credentials...")
      try:
        if login_automated(
          self.driver, ECONOMIST_EMAIL, ECONOMIST_PASSWORD
        ):
          print("Login complete")
          return
      except WebDriverException as e:
        print(f"Automated login error: {e}")
      except Exception as e:
        print(f"Automated login error: {e}")
      print("Automated login failed, falling back to manual login...")

    if NONINTERACTIVE:
      raise RuntimeError(
        "Automated login failed or credentials are missing, and manual "
        "login is disabled (ECONOMISTER_NONINTERACTIVE=true)."
      )

    if not self._is_browser_healthy():
      # Manual login needs a visible window.
      self._restart_browser(headless=False)
    elif self._headless:
      print("Switching to headed Chrome for manual login...")
      self._restart_browser(headless=False)

    self._login_manual()

  def _login_manual(self) -> None:
    """Navigate to login page and wait for manual authentication."""
    print("Navigating to login page...")
    if not _safe_navigate(self.driver, LOGIN_URL):
      raise RuntimeError("Browser tab crashed while opening login page")
    dismiss_cookie_banner(self.driver, timeout=3)
    print("\n" + "=" * 60)
    print("Please log in to The Economist in the browser")
    print("After logging in, press Enter to continue...")
    print("=" * 60 + "\n")
    input()
    dismiss_cookie_banner(self.driver, timeout=3)
    print("Login complete")

  def navigate(self, url: str, wait_time: int = PAGE_LOAD_WAIT_TIME) -> str:
    """Navigate to URL and return page source.

    Args:
        url: URL to navigate to.
        wait_time: Time to wait for page load.

    Returns:
        Page HTML source.
    """
    if not self.driver:
      raise RuntimeError("Browser not initialized. Call setup() first.")

    if not _safe_navigate(self.driver, url):
      raise RuntimeError(f"Browser tab crashed while opening {url}")
    dismiss_cookie_banner(self.driver, timeout=3)
    wait_out_cloudflare(self.driver)
    time.sleep(wait_time)
    return self.driver.page_source

  def quit(self) -> None:
    """Close browser and cleanup."""
    if self.driver:
      try:
        self.driver.quit()
      except Exception:
        pass
      finally:
        self.driver = None
