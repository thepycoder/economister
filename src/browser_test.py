"""Tests for the browser module."""

import unittest
from unittest.mock import Mock, PropertyMock, patch

from selenium.common.exceptions import WebDriverException

from browser import (
  BrowserManager,
  dismiss_cookie_banner,
  is_cloudflare_challenge,
  login_automated,
  _dismiss_sourcepoint_consent,
  _is_still_authenticating,
  _verify_logged_in,
)


class TestBrowserHelpers(unittest.TestCase):
  """Test browser helper functions."""

  def test_is_still_authenticating_login_page(self):
    """Test OAuth detection on Salesforce login URL."""
    url = "https://myaccount.economist.com/s/login/?ec=302"
    self.assertTrue(_is_still_authenticating(url))

  def test_is_still_authenticating_oauth_callback(self):
    """Test OAuth detection on RemoteAccessAuthorizationPage."""
    url = (
      "https://myaccount.economist.com/setup/secur/"
      "RemoteAccessAuthorizationPage.apexp?source=abc"
    )
    self.assertTrue(_is_still_authenticating(url))

  def test_is_still_authenticating_done(self):
    """Test OAuth complete on economist.com."""
    url = "https://www.economist.com/weeklyedition/2026/07/12"
    self.assertFalse(_is_still_authenticating(url))

  def test_is_cloudflare_challenge_detects_interstitial(self):
    """Test Cloudflare challenge title and HTML markers."""
    self.assertTrue(
      is_cloudflare_challenge("Just a moment...", "<html></html>")
    )
    self.assertTrue(
      is_cloudflare_challenge(
        "Weekly edition",
        "<html>cdn-cgi/challenge-platform</html>",
      )
    )
    self.assertFalse(
      is_cloudflare_challenge(
        "The Economist",
        "<html><h1>Leaders</h1></html>",
      )
    )

  def test_dismiss_cookie_banner_clicks_accept(self):
    """Test cookie banner dismissal clicks the accept button."""
    driver = Mock()
    driver.current_url = "https://www.economist.com/"
    button = Mock()
    button.is_displayed.return_value = True
    button.is_enabled.return_value = True
    driver.find_elements.return_value = [button]
    with patch("browser._click_element") as mock_click:
      result = dismiss_cookie_banner(driver, timeout=1)

    self.assertTrue(result)
    mock_click.assert_called_once_with(driver, button)

  def test_dismiss_cookie_banner_no_banner(self):
    """Test cookie banner dismissal when no banner is present."""
    driver = Mock()
    driver.current_url = "https://www.economist.com/"
    driver.find_elements.return_value = []
    with patch("browser._dismiss_onetrust_banner", return_value=False), patch(
      "browser._dismiss_sourcepoint_consent", return_value=False
    ):
      result = dismiss_cookie_banner(driver, timeout=0)

    self.assertFalse(result)

  def test_dismiss_sourcepoint_consent_clicks_accept(self):
    """Test Sourcepoint iframe consent is accepted."""
    driver = Mock()
    iframe = Mock()
    button = Mock()
    iframe.is_displayed.return_value = True
    driver.find_elements.return_value = [iframe]

    with patch("browser._find_element", return_value=button), patch(
      "browser._click_element"
    ) as mock_click:
      result = _dismiss_sourcepoint_consent(driver)

    self.assertTrue(result)
    driver.switch_to.frame.assert_called_once_with(iframe)
    mock_click.assert_called_once_with(driver, button)
    driver.switch_to.default_content.assert_called_once()

  def test_verify_logged_in_accepts_post_oauth_homepage(self):
    """Login verification does not require loading the weekly edition."""
    driver = Mock()
    driver.current_url = "https://www.economist.com/"

    with patch("browser._wait_for_login_complete", return_value=True), patch(
      "browser.dismiss_cookie_banner", return_value=False
    ):
      self.assertTrue(_verify_logged_in(driver))

    driver.get.assert_not_called()

  def test_verify_logged_in_rejects_salesforce_login_page(self):
    """Login verification fails while still on Salesforce."""
    driver = Mock()
    driver.current_url = "https://myaccount.economist.com/s/login/"

    with patch("browser._wait_for_login_complete", return_value=True), patch(
      "browser.dismiss_cookie_banner", return_value=False
    ):
      self.assertFalse(_verify_logged_in(driver))

  @patch("browser._verify_logged_in", return_value=True)
  @patch("browser._click_first", return_value=True)
  @patch("browser._fill_first", return_value=True)
  @patch("browser._wait_for_login_page", return_value=True)
  @patch("browser.dismiss_cookie_banner", return_value=False)
  @patch("browser.time.sleep")
  def test_login_automated_success(
    self,
    mock_sleep,
    mock_dismiss,
    mock_wait_form,
    mock_fill,
    mock_click,
    mock_verify,
  ):
    """Test automated login flow with mocked Selenium interactions."""
    driver = Mock()
    driver.current_url = "https://myaccount.economist.com/s/login/"

    result = login_automated(driver, "user@example.com", "secret")

    self.assertTrue(result)
    driver.get.assert_called()
    self.assertEqual(mock_fill.call_count, 2)
    mock_click.assert_called()
    mock_verify.assert_called_once_with(driver)

  @patch("browser._fill_first", return_value=False)
  @patch("browser._wait_for_login_page", return_value=True)
  @patch("browser.dismiss_cookie_banner", return_value=False)
  @patch("browser.time.sleep")
  @patch("browser.WebDriverWait")
  def test_login_automated_missing_email_field(
    self, mock_wait, mock_sleep, mock_dismiss, mock_wait_form, mock_fill
  ):
    """Test automated login fails when email field is missing."""
    driver = Mock()
    driver.current_url = "https://myaccount.economist.com/s/login/"
    mock_wait.return_value.until.return_value = True

    result = login_automated(driver, "user@example.com", "secret")

    self.assertFalse(result)


class TestBrowserManager(unittest.TestCase):
  """Test BrowserManager class."""

  def setUp(self):
    """Set up test fixtures."""
    self.browser = BrowserManager()

  def tearDown(self):
    """Clean up after tests."""
    # Ensure driver is quit if it exists
    if self.browser.driver:
      try:
        self.browser.driver.quit()
      except:
        pass

  @patch("browser.HEADLESS", True)
  @patch("browser.webdriver.Chrome")
  def test_setup_success(self, mock_chrome, *_headless):
    """Test successful browser setup defaults to headless."""
    mock_driver = Mock()
    mock_chrome.return_value = mock_driver

    self.browser.setup()

    mock_chrome.assert_called_once()
    self.assertEqual(self.browser.driver, mock_driver)
    self.assertTrue(self.browser._headless)

    options = mock_chrome.call_args[1]["options"]
    self.assertIn("--headless=new", options.arguments)
    self.assertTrue(
      any(arg.startswith("--user-agent=") for arg in options.arguments)
    )

  @patch("browser.HEADLESS", False)
  @patch("browser.webdriver.Chrome")
  def test_setup_headed_when_disabled(self, mock_chrome, *_headless):
    """Test headed Chrome when HEADLESS=false."""
    mock_driver = Mock()
    mock_chrome.return_value = mock_driver

    self.browser.setup()

    options = mock_chrome.call_args[1]["options"]
    self.assertNotIn("--headless=new", options.arguments)
    self.assertFalse(self.browser._headless)

  @patch("browser.webdriver.Chrome")
  def test_setup_failure(self, mock_chrome):
    """Test browser setup failure."""
    mock_chrome.side_effect = Exception("ChromeDriver not found")

    with self.assertRaises(RuntimeError) as context:
      self.browser.setup()

    self.assertIn("Failed to start Chrome browser", str(context.exception))
    self.assertIn("ChromeDriver not found", str(context.exception))

  @patch("browser.webdriver.Chrome")
  def test_login_restarts_browser_after_tab_crash(
    self, mock_chrome
  ):
    """Test browser restarts when tab crashes during automated login."""
    mock_driver = Mock()
    mock_chrome.return_value = mock_driver

    browser = BrowserManager()
    browser.setup()
    type(mock_driver).current_url = PropertyMock(
      side_effect=WebDriverException("tab crashed")
    )

    with patch("browser.ECONOMIST_EMAIL", "user@example.com"), patch(
      "browser.ECONOMIST_PASSWORD", "secret"
    ), patch(
      "browser.login_automated",
      side_effect=WebDriverException("tab crashed"),
    ), patch.object(browser, "_restart_browser") as mock_restart, patch.object(
      browser, "_login_manual"
    ) as mock_manual:
      browser.login()

    mock_restart.assert_called_once_with(headless=False)
    mock_manual.assert_called_once()

  @patch("browser.webdriver.Chrome")
  def test_export_requests_session(self, mock_chrome):
    """Test exporting browser cookies to a requests session."""
    mock_driver = Mock()
    mock_driver.get_cookies.return_value = [
      {
        "name": "session",
        "value": "abc123",
        "domain": ".economist.com",
        "path": "/",
      }
    ]
    mock_chrome.return_value = mock_driver

    browser = BrowserManager()
    browser.setup()
    session = browser.export_requests_session()

    self.assertEqual(session.cookies.get("session"), "abc123")
    self.assertIn("Mozilla", session.headers["User-Agent"])

  @patch("browser.webdriver.Chrome")
  def test_export_requests_session_uses_browser_user_agent(self, mock_chrome):
    """Test exported session uses the live Chrome user-agent."""
    mock_driver = Mock()
    mock_driver.get_cookies.return_value = []
    mock_driver.execute_script.return_value = (
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    mock_chrome.return_value = mock_driver

    browser = BrowserManager()
    browser.setup()
    session = browser.export_requests_session()

    self.assertEqual(
      session.headers["User-Agent"],
      mock_driver.execute_script.return_value,
    )

  @patch("browser.HEADLESS", True)
  @patch("browser.ECONOMIST_EMAIL", "")
  @patch("browser.ECONOMIST_PASSWORD", "")
  @patch("browser.input", return_value="")
  @patch("browser.dismiss_cookie_banner", return_value=False)
  @patch("browser.webdriver.Chrome")
  def test_login_manual_fallback(
    self, mock_chrome, mock_dismiss, mock_input, *_patches
  ):
    """Test manual login flow when credentials are absent."""
    mock_driver = Mock()
    mock_chrome.return_value = mock_driver

    self.browser.setup()
    self.browser.login()

    # Headless → headed restart for manual login, then navigate.
    self.assertGreaterEqual(mock_chrome.call_count, 2)
    mock_driver.get.assert_called_with(
      "https://www.economist.com/api/auth/login"
    )
    mock_input.assert_called_once()
    self.assertFalse(self.browser._headless)

  @patch("browser.HEADLESS", True)
  @patch("browser.ECONOMIST_PASSWORD", "secret")
  @patch("browser.ECONOMIST_EMAIL", "user@example.com")
  @patch("browser.login_automated", return_value=True)
  @patch("browser.webdriver.Chrome")
  def test_login_automated_when_credentials_present(
    self, mock_chrome, mock_auto_login, *_patches
  ):
    """Test automated login is used when .env credentials exist."""
    mock_driver = Mock()
    mock_chrome.return_value = mock_driver

    self.browser.setup()
    self.browser.login()

    mock_auto_login.assert_called_once_with(
      mock_driver, "user@example.com", "secret"
    )
    self.assertTrue(self.browser._headless)

  @patch("browser.HEADLESS", True)
  @patch("browser.ECONOMIST_PASSWORD", "secret")
  @patch("browser.ECONOMIST_EMAIL", "user@example.com")
  @patch("browser.input", return_value="")
  @patch("browser.dismiss_cookie_banner", return_value=False)
  @patch("browser.login_automated", return_value=False)
  @patch("browser.webdriver.Chrome")
  def test_login_falls_back_after_automation_fails(
    self,
    mock_chrome,
    mock_auto_login,
    mock_dismiss,
    mock_input,
    *_patches,
  ):
    """Test manual login fallback when automation fails."""
    mock_driver = Mock()
    mock_chrome.return_value = mock_driver

    self.browser.setup()
    self.browser.login()

    mock_auto_login.assert_called_once()
    mock_input.assert_called_once()
    self.assertFalse(self.browser._headless)

  @patch("browser.NONINTERACTIVE", True)
  @patch("browser.HEADLESS", True)
  @patch("browser.ECONOMIST_PASSWORD", "secret")
  @patch("browser.ECONOMIST_EMAIL", "user@example.com")
  @patch("browser.login_automated", return_value=False)
  @patch("browser.webdriver.Chrome")
  def test_login_noninteractive_skips_manual_fallback(
    self, mock_chrome, mock_auto_login, *_patches
  ):
    """Test Docker/NAS runs fail instead of waiting for manual login."""
    mock_driver = Mock()
    mock_chrome.return_value = mock_driver

    self.browser.setup()
    with self.assertRaises(RuntimeError) as context:
      self.browser.login()

    mock_auto_login.assert_called_once()
    self.assertIn("ECONOMISTER_NONINTERACTIVE", str(context.exception))
    self.assertTrue(self.browser._headless)

  def test_login_without_setup(self):
    """Test login without browser setup."""
    with self.assertRaises(RuntimeError) as context:
      self.browser.login()

    self.assertIn("Browser not initialized", str(context.exception))

  @patch("browser.dismiss_cookie_banner", return_value=False)
  @patch("browser.time.sleep")
  @patch("browser.webdriver.Chrome")
  def test_navigate(self, mock_chrome, mock_sleep, mock_dismiss):
    """Test page navigation."""
    mock_driver = Mock()
    mock_driver.page_source = "<html>Test Page</html>"
    mock_chrome.return_value = mock_driver

    self.browser.setup()
    result = self.browser.navigate("https://example.com/page")

    mock_driver.get.assert_called_with("https://example.com/page")
    mock_dismiss.assert_called()
    mock_sleep.assert_called_once_with(5)  # Default wait time
    self.assertEqual(result, "<html>Test Page</html>")

  @patch("browser.dismiss_cookie_banner", return_value=False)
  @patch("browser.time.sleep")
  @patch("browser.webdriver.Chrome")
  def test_navigate_custom_wait(
    self, mock_chrome, mock_sleep, mock_dismiss
  ):
    """Test navigation with custom wait time."""
    mock_driver = Mock()
    mock_driver.page_source = "<html>Test</html>"
    mock_chrome.return_value = mock_driver

    self.browser.setup()
    self.browser.navigate("https://example.com", wait_time=10)

    mock_sleep.assert_called_once_with(10)

  def test_navigate_without_setup(self):
    """Test navigation without browser setup."""
    with self.assertRaises(RuntimeError) as context:
      self.browser.navigate("https://example.com")

    self.assertIn("Browser not initialized", str(context.exception))

  @patch("browser.webdriver.Chrome")
  def test_quit(self, mock_chrome):
    """Test browser cleanup."""
    mock_driver = Mock()
    mock_chrome.return_value = mock_driver

    self.browser.setup()
    self.assertIsNotNone(self.browser.driver)

    self.browser.quit()

    mock_driver.quit.assert_called_once()
    self.assertIsNone(self.browser.driver)

  @patch("browser.webdriver.Chrome")
  def test_quit_with_error(self, mock_chrome):
    """Test browser cleanup with error."""
    mock_driver = Mock()
    mock_driver.quit.side_effect = Exception("Browser already closed")
    mock_chrome.return_value = mock_driver

    self.browser.setup()
    self.browser.quit()  # Should not raise exception

    self.assertIsNone(self.browser.driver)

  def test_quit_without_driver(self):
    """Test quit when no driver exists."""
    self.browser.quit()  # Should not raise exception
    self.assertIsNone(self.browser.driver)

  @patch("browser.atexit.register")
  def test_atexit_registration(self, mock_register):
    """Test that quit is registered with atexit."""
    browser = BrowserManager()
    mock_register.assert_called_once_with(browser.quit)


if __name__ == "__main__":
  unittest.main()
