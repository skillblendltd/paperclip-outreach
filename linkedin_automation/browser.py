"""
Stealth browser wrapper.

Uses undetected-chromedriver to evade LinkedIn's bot detection.
Maintains a persistent Chrome profile so login survives across runs.

The only entry point for anything that opens a webpage. No other
module calls Selenium directly.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from . import config

logger = logging.getLogger(__name__)

# We import undetected_chromedriver lazily so the rest of the module
# can be imported in environments where it isn't installed (e.g. for
# running just the DB init or dashboard).


def _import_uc():
    try:
        import undetected_chromedriver as uc  # type: ignore
        return uc
    except ImportError as e:
        raise RuntimeError(
            "undetected-chromedriver not installed. Run: "
            "pip install undetected-chromedriver selenium"
        ) from e


class Browser:
    """
    Long-lived Chrome session.

    Use as a context manager OR manage lifecycle manually for
    multi-action sessions:

        with Browser() as br:
            br.driver.get("https://linkedin.com")

        # Or:
        br = Browser()
        br.start()
        ...
        br.stop()
    """

    def __init__(self, headless: bool = False):
        self.driver = None
        self._headless = headless or config.CHROME_HEADLESS

    def start(self):
        if self.driver is not None:
            return self
        uc = _import_uc()

        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={config.CHROME_PROFILE_DIR}")
        options.add_argument(f"--window-size={config.CHROME_WINDOW_SIZE[0]},{config.CHROME_WINDOW_SIZE[1]}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-blink-features=AutomationControlled")

        if config.USER_AGENT:
            options.add_argument(f"--user-agent={config.USER_AGENT}")

        # Critical: do NOT use headless. LinkedIn detects it instantly.
        self.driver = uc.Chrome(
            options=options,
            headless=False,
            use_subprocess=True,
        )
        self.driver.set_page_load_timeout(45)
        logger.info("Chrome started with persistent profile at %s", config.CHROME_PROFILE_DIR)
        return self

    def stop(self):
        if self.driver is None:
            return
        try:
            self.driver.quit()
        except Exception as e:
            logger.warning(f"Chrome quit error (ignoring): {e}")
        finally:
            self.driver = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    # ------------------------------------------------------------------
    # Hard-stop / circuit-breaker detection
    # ------------------------------------------------------------------

    def is_blocked(self) -> tuple[bool, str]:
        """
        Check if LinkedIn has blocked us.

        Returns (blocked, reason). If blocked, the runner must STOP.
        """
        if self.driver is None:
            return False, ""
        url = self.driver.current_url or ""
        page_source = ""
        try:
            page_source = self.driver.page_source[:50000]  # First 50KB only
        except Exception:
            pass

        for pattern in config.HARD_STOP_PATTERNS:
            if pattern in url or pattern in page_source:
                return True, pattern

        return False, ""

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def screenshot(self, label: str) -> str:
        """Save screenshot to screenshots/, return path."""
        if self.driver is None:
            return ""
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = config.SCREENSHOTS_DIR / f"{ts}_{label}.png"
        config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.driver.save_screenshot(str(path))
            return str(path)
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            return ""

    def is_logged_in(self) -> bool:
        """Check whether the current session is logged into LinkedIn."""
        if self.driver is None:
            return False
        try:
            self.driver.get("https://www.linkedin.com/feed/")
            time.sleep(3)
            url = self.driver.current_url
            # If redirected to /login or /authwall, we're not logged in
            if "/login" in url or "/authwall" in url or "/uas/login" in url:
                return False
            return "/feed" in url or "linkedin.com/feed" in url
        except Exception as e:
            logger.warning(f"Login check failed: {e}")
            return False


@contextmanager
def browser_session() -> Iterator[Browser]:
    """Shorthand context manager."""
    br = Browser()
    try:
        br.start()
        yield br
    finally:
        br.stop()
