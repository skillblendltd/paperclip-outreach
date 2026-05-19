"""
LinkedIn DM sender.

Two entry points:
  send_dm_from_profile()  - navigate to a profile page, click Message, type, send.
                            Works for both new threads and existing ones (LI opens
                            the existing thread when you click Message on a 1st-degree).
  send_dm_via_messaging() - navigate to /messaging/, search for a name, find the
                            thread, type, send. Use when you don't have the profile URL.

Both return a SendDmResult dataclass.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import human
from .browser import Browser

logger = logging.getLogger(__name__)


@dataclass
class SendDmResult:
    status: str   # 'sent' | 'not_connected' | 'thread_not_found' | 'error' | 'blocked'
    error: str = ""
    screenshot_path: str = ""


# ---------------------------------------------------------------------------
# Shared selectors
# ---------------------------------------------------------------------------

# Compose / message box (appears inside a modal or the messaging pane)
COMPOSE_BOX_SELECTORS = [
    "div.msg-form__contenteditable[contenteditable='true']",
    "div[role='textbox'][data-placeholder]",
    "div.msg-form__contenteditable",
    "div[contenteditable='true'][data-artdeco-is-focused]",
]

# Send button
SEND_BUTTON_SELECTORS = [
    "button.msg-form__send-button[type='submit']",
    "button[aria-label='Send'][type='submit']",
    "button[data-control-name='send']",
    "button.msg-form__send-button",
]


def _find_compose_box(driver, timeout: int = 10):
    """Wait for and return the compose box element."""
    for sel in COMPOSE_BOX_SELECTORS:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            if el.is_displayed():
                return el
        except TimeoutException:
            continue
    return None


def _find_send_button(driver):
    """Find the send button after typing."""
    for sel in SEND_BUTTON_SELECTORS:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed() and btn.is_enabled():
                return btn
        except NoSuchElementException:
            continue
    return None


def _type_and_send(br: Browser, message: str) -> bool:
    """
    Type the message and click Send.
    Returns True on success.
    """
    compose = _find_compose_box(br.driver)
    if not compose:
        logger.error("Compose box not found")
        return False

    human.move_mouse_to(br.driver, compose)
    compose.click()
    human.short_pause()

    # Clear any existing draft
    try:
        compose.send_keys(Keys.CONTROL + "a")
        compose.send_keys(Keys.DELETE)
        human.short_pause()
    except Exception:
        pass

    human.human_type(compose, message)
    human.short_pause()

    send_btn = _find_send_button(br.driver)
    if not send_btn:
        logger.error("Send button not found after typing")
        return False

    human.human_click(br.driver, send_btn)
    human.sleep_range(1.5, 3.0)  # wait for send confirmation

    return True


# ---------------------------------------------------------------------------
# Entry point 1: send from profile page
# ---------------------------------------------------------------------------

def _find_message_button(driver):
    """
    Find the Message button on a LinkedIn profile page.
    Tries multiple strategies since LinkedIn changes its DOM frequently.
    Returns the button element or None.
    """
    # Strategy 1: wait for any button with aria-label containing 'Message' to appear
    try:
        btn = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-label*='Message']"))
        )
        if btn and btn.is_displayed():
            return btn
    except TimeoutException:
        pass

    # Strategy 2: scroll down a bit (action buttons sometimes below the fold) then retry
    try:
        driver.execute_script("window.scrollBy(0, 200)")
        time.sleep(1)
        for btn in driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Message']"):
            if btn.is_displayed():
                return btn
    except Exception:
        pass

    # Strategy 3: text-based search across all buttons
    try:
        for btn in driver.find_elements(By.TAG_NAME, "button"):
            txt = (btn.text or "").strip()
            aria = (btn.get_attribute("aria-label") or "").strip()
            if "Message" in txt or "Message" in aria:
                if btn.is_displayed():
                    return btn
    except Exception:
        pass

    # Strategy 4: LinkedIn sometimes wraps Message in an <a> tag or a span
    try:
        for sel in [
            "a[data-control-name='message']",
            "a[href*='/messaging/thread/']",
            "span[aria-label*='Message']",
        ]:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    return el
    except Exception:
        pass

    # Strategy 5: check if 'Message' appears in a "More" dropdown menu
    try:
        more_btns = driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='More']")
        for more_btn in more_btns:
            if more_btn.is_displayed():
                more_btn.click()
                time.sleep(1)
                for item in driver.find_elements(By.CSS_SELECTOR, "[role='menuitem'], li"):
                    if "Message" in (item.text or ""):
                        return item
    except Exception:
        pass

    return None


def send_dm_from_profile(
    br: Browser,
    profile_url: str,
    message: str,
    person_name: str = "",
) -> SendDmResult:
    """
    Navigate to a LinkedIn profile, click Message, type, send.

    Works for 1st-degree connections (Message button is always visible).
    For existing threads, LinkedIn opens the thread automatically.
    Falls back to messaging inbox search if Message button not found.
    """
    # Normalise URL
    if not profile_url.startswith("http"):
        profile_url = "https://www.linkedin.com/in/" + profile_url

    logger.info(f"Navigating to profile: {profile_url}")
    br.driver.get(profile_url)
    human.page_load_pause()

    # Scroll back to top - Message button is in the profile header
    try:
        br.driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(0.5)
    except Exception:
        pass

    # Check for hard-stop
    blocked, reason = br.is_blocked()
    if blocked:
        return SendDmResult(status="blocked", error=reason)

    # Check for 404 / private
    current_url = br.driver.current_url or ""
    if "/404" in current_url or "unavailable" in current_url.lower():
        return SendDmResult(status="error", error="Profile not found or unavailable")

    # Extract name from h1 if not provided (used for fallback)
    if not person_name:
        try:
            person_name = br.driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
        except Exception:
            pass

    # Find Message button
    msg_btn = _find_message_button(br.driver)

    if not msg_btn:
        # Log visible buttons for debugging
        try:
            btns = br.driver.find_elements(By.TAG_NAME, "button")
            btn_texts = [(b.get_attribute("aria-label") or b.text or "").strip() for b in btns[:15] if b.is_displayed()]
            logger.warning(f"No Message button on profile. Visible buttons: {btn_texts}")
        except Exception:
            pass
        # Fallback: try messaging inbox search
        if person_name:
            logger.info(f"Falling back to messaging inbox search for: {person_name}")
            return send_dm_via_messaging(br, person_name, message)
        screenshot = br.screenshot("dm_no_message_button")
        return SendDmResult(
            status="not_connected",
            error="Message button not found - not a 1st-degree connection or profile is restricted",
            screenshot_path=screenshot,
        )

    logger.info("Found Message button - clicking")
    human.human_click(br.driver, msg_btn)
    human.sleep_range(1.5, 3.0)

    success = _type_and_send(br, message)
    if not success:
        screenshot = br.screenshot("dm_send_failed")
        return SendDmResult(
            status="error",
            error="Could not find compose box or send button after clicking Message",
            screenshot_path=screenshot,
        )

    screenshot = br.screenshot("dm_sent_ok")
    logger.info(f"DM sent to {profile_url}")
    return SendDmResult(status="sent", screenshot_path=screenshot)


# ---------------------------------------------------------------------------
# Entry point 2: send via /messaging/ (when you only have a name)
# ---------------------------------------------------------------------------

MESSAGING_SEARCH_SELECTORS = [
    "input[placeholder='Search messages']",
    "input[aria-label='Search messages']",
    "input[placeholder*='Search']",
]

CONVERSATION_ITEM_SELECTORS = [
    ".msg-conversation-listitem__link",
    "a.msg-conversations-container__conversations-list-item-link",
    "li.msg-conversation-listitem a",
    "[data-control-name='view_conversation']",
]


def send_dm_via_messaging(
    br: Browser,
    person_name: str,
    message: str,
) -> SendDmResult:
    """
    Navigate to LinkedIn /messaging/, search for person_name,
    click their thread, type and send.

    Use when you don't have the profile URL.
    """
    logger.info(f"Opening messaging page to find thread with: {person_name}")
    br.driver.get("https://www.linkedin.com/messaging/")
    human.page_load_pause()
    human.random_scroll(br.driver)

    blocked, reason = br.is_blocked()
    if blocked:
        return SendDmResult(status="blocked", error=reason)

    # Find the search box
    search_box = None
    for sel in MESSAGING_SEARCH_SELECTORS:
        try:
            search_box = WebDriverWait(br.driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            if search_box.is_displayed():
                break
            search_box = None
        except TimeoutException:
            continue

    if not search_box:
        screenshot = br.screenshot("dm_no_search_box")
        return SendDmResult(
            status="error",
            error="Could not find messaging search box",
            screenshot_path=screenshot,
        )

    # Search for the person - type then press Enter to trigger search
    human.human_click(br.driver, search_box)
    human.short_pause()
    human.human_type(search_box, person_name)
    human.sleep_range(2.0, 3.0)
    search_box.send_keys(Keys.RETURN)
    human.sleep_range(2.0, 3.5)  # wait for search results to load

    first_name = person_name.split()[0].lower()
    full_name_lower = person_name.lower()

    def _find_thread_link():
        # 1. Standard conversation list items
        for sel in CONVERSATION_ITEM_SELECTORS:
            try:
                items = br.driver.find_elements(By.CSS_SELECTOR, sel)
                for item in items:
                    if full_name_lower in (item.text or "").lower() or first_name in (item.text or "").lower():
                        return item
            except (NoSuchElementException, StaleElementReferenceException):
                continue

        # 2. Search result items (LinkedIn shows these differently after a search)
        search_result_selectors = [
            "a[href*='/messaging/thread/']",
            ".msg-search-results__list-item a",
            ".msg-search-results a",
            "ul.msg-search-results__list li a",
        ]
        for sel in search_result_selectors:
            try:
                items = br.driver.find_elements(By.CSS_SELECTOR, sel)
                for item in items:
                    if full_name_lower in (item.text or "").lower() or first_name in (item.text or "").lower():
                        return item
            except (NoSuchElementException, StaleElementReferenceException):
                continue

        # 3. Any anchor whose text contains the name anywhere on the page
        try:
            for a in br.driver.find_elements(By.TAG_NAME, "a"):
                txt = (a.text or "").lower()
                if full_name_lower in txt or (first_name in txt and len(txt) < 80):
                    href = a.get_attribute("href") or ""
                    if "messaging" in href or "in/" in href:
                        return a
        except Exception:
            pass

        # 4. Any li containing the name
        try:
            for li in br.driver.find_elements(By.CSS_SELECTOR, "li"):
                if full_name_lower in (li.text or "").lower():
                    links = li.find_elements(By.TAG_NAME, "a")
                    if links:
                        return links[0]
        except Exception:
            pass

        return None

    thread_link = _find_thread_link()

    if not thread_link:
        screenshot = br.screenshot("dm_thread_not_found")
        # Log all visible text for debugging
        try:
            page_text = br.driver.find_element(By.TAG_NAME, "body").text[:1000]
            logger.warning(f"Page text after search: {page_text}")
        except Exception:
            pass
        return SendDmResult(
            status="thread_not_found",
            error=f"Could not find messaging thread for '{person_name}'",
            screenshot_path=screenshot,
        )

    logger.info(f"Found thread for '{person_name}' - clicking")
    human.human_click(br.driver, thread_link)
    human.sleep_range(1.5, 2.5)

    success = _type_and_send(br, message)
    if not success:
        screenshot = br.screenshot("dm_send_failed_messaging")
        return SendDmResult(
            status="error",
            error="Could not find compose box or send button in thread",
            screenshot_path=screenshot,
        )

    screenshot = br.screenshot("dm_sent_messaging_ok")
    logger.info(f"DM sent to '{person_name}' via messaging")
    return SendDmResult(status="sent", screenshot_path=screenshot)
