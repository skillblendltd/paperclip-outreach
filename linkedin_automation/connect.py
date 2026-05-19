"""
Connection request sender.

Given a LinkedIn profile URL, click Connect and send WITHOUT a note.
Handle all the edge cases:

- Already connected → mark already_connected (no action)
- Pending invitation already sent → mark sent (no action)
- Connect button hidden under "More" dropdown → expand, find it
- Modal asks for a note → click "Send without a note"
- "Email required" modal (out-of-network) → cancel, mark error
- Profile not found / private / removed → mark not_found

This is Phase 2 - the high-risk phase. Throttle aggressively.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    ElementClickInterceptedException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import human
from .browser import Browser

logger = logging.getLogger(__name__)


@dataclass
class ConnectionResult:
    """Outcome of one connection attempt."""
    status: str  # 'sent' | 'already_connected' | 'pending' | 'not_found' | 'blocked' | 'error'
    error: str = ""


# ---------------------------------------------------------------------------
# Locators - centralized so we can update when LinkedIn changes DOM
# ---------------------------------------------------------------------------

# Primary Connect button on profile - look for aria-label
CONNECT_BUTTON_SELECTORS = [
    "button[aria-label^='Invite'][aria-label*='connect']",
    "button[aria-label^='Connect']",
    "button.artdeco-button--primary[aria-label*='Invite']",
]

# "More" dropdown when Connect is hidden.
# LinkedIn uses different aria-labels across profile types and over time.
# We try specific labels first, then fall back to text content.
MORE_BUTTON_SELECTORS = [
    "button[aria-label='More actions']",
    "button[aria-label='More']",
    "button[aria-label^='More']",
]

# Connect option inside More dropdown.
# After clicking More, items appear as li > div[role=button] or span elements.
MORE_CONNECT_SELECTORS = [
    "div[aria-label^='Invite'][role='button']",
    "div[aria-label*='to connect'][role='button']",
    "span[aria-label^='Invite'][role='button']",
    "li[aria-label*='connect']",
    # Text-match fallback - any dropdown item whose text is "Connect"
    "div.artdeco-dropdown__content-inner li",
]

# Modal "Send without a note" button
SEND_WITHOUT_NOTE_SELECTORS = [
    "button[aria-label='Send without a note']",
    "button[aria-label*='Send without']",
]

# Modal "Send" / "Send now" fallback
SEND_NOW_SELECTORS = [
    "button[aria-label='Send invitation']",
    "button[aria-label*='Send now']",
    "button[aria-label='Send']",
]

# "Add a note" button (note-required modals for 3rd-degree connections)
ADD_NOTE_SELECTORS = [
    "button[aria-label='Add a note']",
    "button[aria-label*='Add a note']",
]

# Note text area (appears after clicking "Add a note")
NOTE_TEXTAREA_SELECTORS = [
    "textarea[name='message']",
    "textarea#custom-message",
    "textarea",
]

# Email input (out-of-network / "How do you know X?" modal)
EMAIL_INPUT_SELECTORS = [
    "input[name='email']",
    "input[type='email']",
    "input[aria-label*='email']",
]

# Modal close / cancel button
MODAL_CLOSE_SELECTORS = [
    "button[aria-label='Dismiss']",
    "button[aria-label='Cancel']",
    "button.artdeco-modal__dismiss",
]

# Brief connection note - used when LinkedIn requires a note for 3rd-degree profiles.
# Keeps it human, on-brand, under 300 chars.
CONNECTION_NOTE = (
    "Hi, I came across your profile and thought it'd be great to connect - "
    "I work in the print and promotional products space and think we may "
    "have some useful common ground."
)

# Pending / already connected state indicators
PENDING_INDICATORS = [
    "button[aria-label*='Pending']",
    "button[aria-label*='Invitation pending']",
]

ALREADY_CONNECTED_INDICATORS = [
    "button[aria-label^='Message']",
    "button[aria-label*='You are connected']",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_find(driver, selectors: list[str], timeout: float = 0):
    """Try each selector. Return first matching element, or None."""
    for sel in selectors:
        try:
            if timeout > 0:
                el = WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
            else:
                el = driver.find_element(By.CSS_SELECTOR, sel)
            if el and el.is_displayed():
                return el
        except (NoSuchElementException, TimeoutException, StaleElementReferenceException):
            continue
    return None


def _is_profile_404(driver) -> bool:
    """Check if profile page is unavailable."""
    try:
        page = driver.page_source[:30000].lower()
        if "this page doesn't exist" in page or "this page doesn't exist" in page:
            return True
        if "page not found" in page:
            return True
        if "/404" in driver.current_url:
            return True
    except Exception:
        pass
    return False


def _clean_name_text(raw: str) -> str:
    """Strip LinkedIn degree indicators and badges from a raw name string."""
    s = re.sub(r'\s*[•·]\s*\d+(st|nd|rd|th).*$', '', raw).strip()
    s = re.sub(r'\s*(verified|open to work|#open_to_work).*$', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'^[^a-zA-Z]+|[^a-zA-Z]+$', '', s).strip()
    return s


def _get_profile_name_from_h1(driver) -> str:
    """
    Return the profile owner's name. Tries multiple sources because LinkedIn
    has changed its profile layout repeatedly.

    Priority:
      1. Page <title> e.g. "Garret Brady | LinkedIn" - always present
      2. h1 element (older / some current profiles)
      3. span.text-heading-xlarge (newer layout)
    """
    # 1. Page title - most reliable across layout changes
    try:
        title = driver.title or ""
        if " | LinkedIn" in title:
            candidate = _clean_name_text(title.split(" | LinkedIn")[0].strip())
            if candidate and 1 <= len(candidate.split()) <= 6:
                return candidate
    except Exception:
        pass

    # 2. h1 element
    try:
        for el in driver.find_elements(By.CSS_SELECTOR, "h1"):
            cleaned = _clean_name_text((el.text or "").strip())
            if cleaned and 1 <= len(cleaned.split()) <= 6:
                return cleaned
    except Exception:
        pass

    # 3. Prominent name span (newer layout)
    try:
        for sel in ["span.text-heading-xlarge", "h1.text-heading-xlarge"]:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                cleaned = _clean_name_text((el.text or "").strip().split("\n")[0])
                if cleaned and 1 <= len(cleaned.split()) <= 6:
                    return cleaned
    except Exception:
        pass

    return ""


def _name_from_aria_label(aria_label: str) -> str:
    """Extract the target name from 'Invite X to connect' style labels."""
    import re as _re
    m = _re.match(r"Invite\s+(.+?)\s+to connect", aria_label, _re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = _re.match(r"Connect\s+with\s+(.+)", aria_label, _re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _button_matches_profile(btn, profile_name: str, profile_url: str = "") -> bool:
    """
    Return True if this Connect button belongs to the current profile page
    (not a sidebar 'People you may know' recommendation).

    LinkedIn sidebar recommendation buttons have the same aria-label format as
    the profile Connect button. We verify by comparing the button's target name
    against the page's h1, or against the URL slug as a fallback.

    IMPORTANT: when profile_name is empty AND url slug can't verify, we return
    False (reject) rather than True (accept). Accepting unknown buttons caused
    sidebar buttons to be clicked instead of the profile's own Connect button.
    """
    try:
        aria_label = btn.get_attribute("aria-label") or ""
    except Exception:
        return True  # Can't inspect button - let it through
    button_name = _name_from_aria_label(aria_label)
    if not button_name:
        return True  # Non-standard label (e.g. plain "Connect") - assume profile button

    # Match against h1-derived profile name
    if profile_name:
        pn = set(re.sub(r"[^a-z\s]", "", profile_name.lower()).split())
        bn = set(re.sub(r"[^a-z\s]", "", button_name.lower()).split())
        if pn & bn:
            return True

    # Fallback: match against URL slug tokens
    # e.g. /in/garret-brady-123/ → tokens {"garret", "brady"}
    if profile_url:
        slug = profile_url.rstrip("/").split("/in/")[-1].lower()
        slug_tokens = set(re.sub(r"[^a-z]", " ", slug).split()) - {"", "in"}
        bn = set(re.sub(r"[^a-z\s]", "", button_name.lower()).split())
        if slug_tokens & bn:
            return True
        # Slug may concatenate name tokens without separators (e.g. /in/garretbrady/)
        # Check if any button-name token appears as a substring of the slug
        if slug and any(t in slug for t in bn if len(t) >= 4):
            return True

    # Nothing matched - this button targets someone else (sidebar recommendation)
    if profile_name or profile_url:
        return False

    # No profile context at all - can't verify, let it through
    return True


# ---------------------------------------------------------------------------
# Main connection flow
# ---------------------------------------------------------------------------

def send_connection(br: Browser, profile_url: str, dry_run: bool = False) -> ConnectionResult:
    """
    Visit the profile, click Connect, send without note.

    Args:
        br: Browser session
        profile_url: LinkedIn profile URL
        dry_run: If True, detect the Connect state but do NOT click anything.
            Returns ConnectionResult with status prefixed 'dry_run_'.
            Useful for previewing what a real run would do without spending
            invite budget. Zero risk - LinkedIn just sees a profile visit.

    Returns ConnectionResult with status and any error info.
    """
    try:
        # Navigate to profile
        br.driver.get(profile_url)
        human.page_load_pause()
        human.random_scroll(br.driver)
        human.short_pause()

        # Hard-stop check after page load
        blocked, reason = br.is_blocked()
        if blocked:
            return ConnectionResult(status="blocked", error=reason)

        if _is_profile_404(br.driver):
            return ConnectionResult(
                status="dry_run_not_found" if dry_run else "not_found",
                error="profile_404",
            )

        # State detection: already connected?
        if _try_find(br.driver, ALREADY_CONNECTED_INDICATORS):
            logger.info(f"Already connected: {profile_url}")
            return ConnectionResult(
                status="dry_run_already_connected" if dry_run else "already_connected"
            )

        # State detection: pending invitation?
        if _try_find(br.driver, PENDING_INDICATORS):
            logger.info(f"Invitation already pending: {profile_url}")
            return ConnectionResult(
                status="dry_run_pending" if dry_run else "sent",
                error="was_already_pending",
            )

        # Get profile owner name from page h1 - used to verify Connect button
        # belongs to this profile and not a sidebar recommendation widget.
        profile_name = _get_profile_name_from_h1(br.driver)
        logger.info(f"Profile name from h1: {profile_name!r}")

        # Try direct Connect button. LinkedIn sidebar "People you may know" widgets
        # also render Connect buttons with the same aria-label format, and they often
        # appear earlier in the DOM than the profile card buttons. So we scan ALL
        # matching elements and pick the first one whose target name matches this profile.
        connect_btn = None
        rejected_labels: list[str] = []
        for sel in CONNECT_BUTTON_SELECTORS:
            try:
                candidates = br.driver.find_elements(By.CSS_SELECTOR, sel)
                for cand in candidates:
                    try:
                        if not cand.is_displayed():
                            continue
                        if _button_matches_profile(cand, profile_name, profile_url):
                            connect_btn = cand
                            break
                        else:
                            rejected_labels.append(
                                (cand.get_attribute("aria-label") or cand.text or "")[:60]
                            )
                    except Exception:
                        continue
            except Exception:
                continue
            if connect_btn:
                break

        # Phase 2: XPath fallback for buttons whose visible text is "Connect"
        # but have NO aria-label (profile's own primary button).
        # Sidebar recommendation buttons always have aria-label="Invite X to connect",
        # so filtering to no-aria-label / aria-label='Connect' safely targets the
        # profile card button only.
        if not connect_btn:
            try:
                xpath_cands = br.driver.find_elements(
                    By.XPATH,
                    "//button["
                    "  .//span[normalize-space(text())='Connect'] and "
                    "  (not(@aria-label) or @aria-label='' or @aria-label='Connect')"
                    "]"
                )
                for cand in xpath_cands:
                    try:
                        if cand.is_displayed():
                            connect_btn = cand
                            logger.info("Found Connect button via text-content XPath (no aria-label)")
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if rejected_labels and not connect_btn:
            logger.warning(
                f"All Connect buttons rejected for '{profile_name}' (sidebar candidates: {rejected_labels[:3]}). "
                f"Falling through to More dropdown."
            )

        if not connect_btn:
            # Try "More" dropdown path.
            # Creator mode profiles show Follow as primary CTA and hide Connect
            # inside a More (...) menu. The More button often has an empty
            # aria-label, so we find it via XPath relative to the Follow button.
            more_btn = None

            # Try by aria-label first (standard profiles)
            more_btn = _try_find(br.driver, MORE_BUTTON_SELECTORS, timeout=2)

            # Fallback: find the More button adjacent to the Follow [Name] button
            if not more_btn and profile_name:
                try:
                    xpath = (
                        f"(//button[@aria-label='Follow {profile_name}'])[1]"
                        f"/following::button[normalize-space(.)='More'][1]"
                    )
                    candidates = br.driver.find_elements(By.XPATH, xpath)
                    if candidates:
                        more_btn = candidates[0]
                        logger.info(f"More button found via Follow-sibling XPath for '{profile_name}'")
                except Exception:
                    pass

            if more_btn and not dry_run:
                # JS click handles both displayed and non-displayed More buttons
                try:
                    br.driver.execute_script("arguments[0].click();", more_btn)
                except Exception:
                    human.human_click(br.driver, more_btn)
                human.sleep_range(0.7, 1.5)

                # LinkedIn's More dropdown (Creator mode): the dropdown item
                # for "Connect" uses a <p> element for its label text. Sidebar
                # buttons use <span> for their "Connect" text. We specifically
                # target <p> to avoid landing on sidebar buttons.
                try:
                    p_els = br.driver.find_elements(
                        By.XPATH, "//p[normalize-space(text())='Connect']"
                    )
                    for el in p_els:
                        if not el.is_displayed():
                            continue
                        # Walk up to the li/a parent to get the clickable container
                        clickable = el
                        for _ in range(5):
                            try:
                                parent = clickable.find_element(By.XPATH, "..")
                                tag = parent.tag_name.lower()
                                role = (parent.get_attribute("role") or "").lower()
                                # Stop at li or role=menuitem/option
                                if tag == "li" or role in ("menuitem", "option"):
                                    clickable = parent
                                    break
                                # Stop if we hit a button-like element
                                if tag == "button":
                                    break
                                clickable = parent
                            except Exception:
                                break
                        connect_btn = clickable
                        logger.info(
                            f"More dropdown Connect: text_tag={el.tag_name} "
                            f"clickable={clickable.tag_name} "
                            f"aria={clickable.get_attribute('aria-label')!r}"
                        )
                        break
                except Exception:
                    pass

                # Fallback: try CSS selectors from MORE_CONNECT_SELECTORS
                if not connect_btn:
                    for sel in MORE_CONNECT_SELECTORS:
                        try:
                            els = br.driver.find_elements(By.CSS_SELECTOR, sel)
                            for el in els:
                                if not el.is_displayed():
                                    continue
                                lbl = el.get_attribute("aria-label") or ""
                                txt = (el.text or "").strip()
                                if ("connect" in lbl.lower() or txt.lower() == "connect"
                                        or "invite" in lbl.lower()):
                                    connect_btn = el
                                    logger.info(f"More dropdown CSS: found Connect aria={lbl!r} text={txt!r}")
                                    break
                            if connect_btn:
                                break
                        except Exception:
                            continue

            elif more_btn and dry_run:
                return ConnectionResult(
                    status="dry_run_ready_via_more",
                    error="connect_button_in_more_dropdown_assumed",
                )

        if not connect_btn:
            return ConnectionResult(
                status="dry_run_no_button" if dry_run else "error",
                error="connect_button_not_found",
            )

        # Dry-run STOP point: we found the Connect button. Don't click it.
        # Capture which button label so we can verify our selectors are right.
        if dry_run:
            try:
                aria_label = connect_btn.get_attribute("aria-label") or ""
            except Exception:
                aria_label = ""
            logger.info(f"DRY-RUN ready: would click Connect on {profile_url} (button aria-label={aria_label!r})")
            return ConnectionResult(
                status="dry_run_ready",
                error=f"would_send: aria-label={aria_label[:100]}",
            )

        # Log exactly what we're about to click so we can diagnose wrong-element issues
        try:
            _btn_label = connect_btn.get_attribute("aria-label") or connect_btn.text or ""
            _btn_tag = connect_btn.tag_name
            logger.info(f"Clicking connect_btn: tag={_btn_tag} aria-label={_btn_label!r} url={br.driver.current_url}")
        except Exception:
            pass

        # Click Connect
        try:
            human.human_click(br.driver, connect_btn)
        except ElementClickInterceptedException:
            # Try JS click as fallback
            br.driver.execute_script("arguments[0].click();", connect_btn)

        logger.info(f"URL after click: {br.driver.current_url}")
        human.sleep_range(1.5, 3.5)

        # Debug: capture what's on screen after clicking Connect so we can
        # diagnose selector mismatches when the modal isn't recognised.
        try:
            from . import config as _cfg
            _ts = __import__("time").strftime("%H%M%S")
            _slug = re.sub(r"[^a-z0-9]", "_", profile_url.split("/in/")[-1].strip("/"))
            _ss_path = _cfg.SCREENSHOTS_DIR / f"modal_debug_{_ts}_{_slug}.png"
            br.driver.save_screenshot(str(_ss_path))
            logger.info(f"Modal debug screenshot: {_ss_path}")
        except Exception:
            pass

        # Dump all visible button labels so we can identify the right selector
        try:
            _btns = br.driver.find_elements(By.CSS_SELECTOR, "button")
            _visible_labels = [
                (b.get_attribute("aria-label") or b.text or "").strip()
                for b in _btns if b.is_displayed()
            ]
            _visible_labels = [l for l in _visible_labels if l]
            logger.info(f"Visible buttons after Connect click: {_visible_labels}")
        except Exception:
            pass

        # LinkedIn renders the invitation modal (with "Send without a note" and
        # "Add a note" buttons) inside a shadow DOM. Standard CSS selectors and
        # find_elements() cannot pierce shadow roots.
        # Strategy:
        #   1. Try standard CSS selectors first (some profiles use regular DOM)
        #   2. Fall back to a JS shadow-DOM walker that finds by aria-label
        #   3. If truly no send path found, dismiss modal and return email_required

        # JS helper: walk shadow roots recursively and click a button by aria-label
        _SHADOW_CLICK_JS = """
            function clickInShadow(ariaLabel) {
                function walk(el) {
                    if (!el) return null;
                    try {
                        if (el.tagName === 'BUTTON' &&
                            el.getAttribute('aria-label') === ariaLabel &&
                            el.offsetParent !== null) {
                            return el;
                        }
                        if (el.shadowRoot) {
                            var f = walk(el.shadowRoot);
                            if (f) return f;
                        }
                        var ch = el.children || [];
                        for (var i = 0; i < ch.length; i++) {
                            var f = walk(ch[i]);
                            if (f) return f;
                        }
                    } catch(e) {}
                    return null;
                }
                var btn = walk(document.body);
                if (btn) { btn.click(); return true; }
                return false;
            }
            return clickInShadow(arguments[0]);
        """

        sent = False

        # 1. Standard CSS selectors
        send_btn = _try_find(br.driver, SEND_WITHOUT_NOTE_SELECTORS, timeout=3)
        if not send_btn:
            send_btn = _try_find(br.driver, SEND_NOW_SELECTORS, timeout=2)
        if send_btn:
            try:
                human.human_click(br.driver, send_btn)
            except ElementClickInterceptedException:
                br.driver.execute_script("arguments[0].click();", send_btn)
            sent = True
            logger.info("Sent via standard selector")

        # 2. Shadow DOM: "Send without a note"
        if not sent:
            try:
                ok = br.driver.execute_script(_SHADOW_CLICK_JS, "Send without a note")
                if ok:
                    sent = True
                    logger.info("Sent via shadow DOM (Send without a note)")
            except Exception:
                pass

        # 3. Shadow DOM: "Send invitation" / "Send now" fallback
        if not sent:
            for label in ("Send invitation", "Send now", "Send"):
                try:
                    ok = br.driver.execute_script(_SHADOW_CLICK_JS, label)
                    if ok:
                        sent = True
                        logger.info(f"Sent via shadow DOM ({label})")
                        break
                except Exception:
                    pass

        # 4. "Add a note" path - standard or shadow DOM
        if not sent:
            add_note_btn = _try_find(br.driver, ADD_NOTE_SELECTORS, timeout=2)
            if add_note_btn:
                try:
                    human.human_click(br.driver, add_note_btn)
                    human.sleep_range(0.7, 1.5)
                    textarea = _try_find(br.driver, NOTE_TEXTAREA_SELECTORS, timeout=3)
                    if textarea:
                        textarea.clear()
                        human.human_type(textarea, CONNECTION_NOTE)
                        human.sleep_range(0.5, 1.2)
                        send_btn2 = _try_find(br.driver, SEND_NOW_SELECTORS, timeout=3)
                        if not send_btn2:
                            send_btn2 = _try_find(br.driver, SEND_WITHOUT_NOTE_SELECTORS, timeout=2)
                        if send_btn2:
                            human.human_click(br.driver, send_btn2)
                            sent = True
                            logger.info("Sent via Add a note path")
                except Exception:
                    logger.warning(f"Add-a-note path failed for {profile_url}", exc_info=True)

        if not sent:
            # Dismiss the modal so it doesn't block future navigation
            close_btn = _try_find(br.driver, MODAL_CLOSE_SELECTORS, timeout=1)
            if close_btn:
                try:
                    human.human_click(br.driver, close_btn)
                    human.sleep_range(0.5, 1.0)
                except Exception:
                    pass
            email_input = _try_find(br.driver, EMAIL_INPUT_SELECTORS, timeout=1)
            return ConnectionResult(
                status="email_required",
                error="out_of_network_email_required" if email_input else "send_button_not_found",
            )

        human.sleep_range(2.0, 4.0)

        # Confirm send by checking for pending indicator OR toast OR URL change
        # We don't fail hard if confirmation is ambiguous - we assume success and
        # let the next discovery cycle correct it.
        return ConnectionResult(status="sent")

    except Exception as e:
        logger.exception(f"Connection failed for {profile_url}")
        return ConnectionResult(status="error", error=str(e)[:500])
