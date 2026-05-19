"""
Human simulation primitives.

Everything that produces a delay, mouse movement, scroll, or keystroke
goes through this module. The goal: make our automated actions
indistinguishable from a tired human clicking through LinkedIn after lunch.

Critical: never sleep with a fixed value. Always randomize.
"""

from __future__ import annotations

import logging
import random
import time

from . import config

logger = logging.getLogger(__name__)

# Lazy selenium imports so DB-only commands work without selenium installed
try:
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    _SELENIUM_AVAILABLE = True
except ImportError:
    ActionChains = None  # type: ignore
    WebDriver = object  # type: ignore
    WebElement = object  # type: ignore
    _SELENIUM_AVAILABLE = False


def sleep_range(min_sec: float, max_sec: float) -> float:
    """Sleep for a random duration. Returns the actual sleep time."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def short_pause() -> float:
    """Tiny pause for between-action breathing (200-800ms)."""
    return sleep_range(0.2, 0.8)


def page_load_pause() -> float:
    """Pause after a page navigation, mimicking reading the new page."""
    return sleep_range(config.PAGE_LOAD_PAUSE_MIN_SEC, config.PAGE_LOAD_PAUSE_MAX_SEC)


def discovery_pause() -> float:
    """Pause between discovery searches."""
    delay = sleep_range(config.DISCOVERY_DELAY_MIN_SEC, config.DISCOVERY_DELAY_MAX_SEC)
    logger.debug(f"Discovery pause: {delay:.1f}s")
    return delay


def connection_pause() -> float:
    """Pause between connection requests. Longer = safer."""
    delay = sleep_range(config.CONNECTION_DELAY_MIN_SEC, config.CONNECTION_DELAY_MAX_SEC)
    logger.debug(f"Connection pause: {delay:.1f}s")
    return delay


def session_break() -> float:
    """Mid-session longer break (5-15 min) to look like a coffee break."""
    delay = sleep_range(config.SESSION_PAUSE_MIN_SEC, config.SESSION_PAUSE_MAX_SEC)
    logger.info(f"Session break: {delay/60:.1f} min")
    return delay


def random_scroll(driver: WebDriver) -> None:
    """Randomly scroll the page. Skip with some probability."""
    if random.random() > config.SCROLL_PROBABILITY:
        return
    distance = random.randint(config.SCROLL_DISTANCE_MIN, config.SCROLL_DISTANCE_MAX)
    direction = random.choice([1, 1, 1, -1])  # Mostly scroll down
    driver.execute_script(f"window.scrollBy(0, {distance * direction})")
    short_pause()


def move_mouse_to(driver, element) -> None:
    """
    Move mouse to element in multiple steps - never instant.

    This is the single most important anti-detection signal: humans
    don't teleport their mouse to an element, they move it across the screen.
    """
    if not _SELENIUM_AVAILABLE:
        raise RuntimeError("selenium not installed - cannot perform mouse actions")
    actions = ActionChains(driver)
    actions.move_to_element(element)
    actions.pause(random.uniform(0.1, 0.4))
    actions.perform()
    short_pause()


def human_click(driver: WebDriver, element: WebElement) -> None:
    """Move mouse to element, pause, then click."""
    move_mouse_to(driver, element)
    sleep_range(0.3, 0.9)
    element.click()
    short_pause()


def human_type(element: WebElement, text: str) -> None:
    """Type with realistic per-character delays."""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(
            config.TYPING_DELAY_MIN_SEC,
            config.TYPING_DELAY_MAX_SEC
        ))


def jitter_viewport(driver: WebDriver) -> None:
    """Slight random scroll up/down to simulate restless reading."""
    if random.random() < 0.3:
        random_scroll(driver)
