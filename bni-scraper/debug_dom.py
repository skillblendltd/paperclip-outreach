#!/usr/bin/env python3
"""Quick debug script to inspect BNI Connect DOM structure."""

import time
from playwright.sync_api import sync_playwright

BNI_URL = "https://www.bniconnectglobal.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(BNI_URL)

    input("\n>>> Log in and search, then press Enter here... ")

    # Dump the outer HTML structure of the results area
    info = page.evaluate("""
        () => {
            const results = [];

            // Check for standard table
            const tables = document.querySelectorAll('table');
            results.push(`Tables found: ${tables.length}`);
            tables.forEach((t, i) => {
                results.push(`  table[${i}]: rows=${t.querySelectorAll('tr').length}, class="${t.className}"`);
            });

            // Check for links with 'member' or 'profile'
            const memberLinks = document.querySelectorAll('a');
            const profileLinks = [];
            memberLinks.forEach(a => {
                const href = a.href || '';
                if (href.includes('member') || href.includes('profile') || href.includes('Member')) {
                    profileLinks.push({href: href, text: a.innerText.trim().substring(0, 50)});
                }
            });
            results.push(`\\nProfile-like links: ${profileLinks.length}`);
            profileLinks.slice(0, 5).forEach(l => {
                results.push(`  "${l.text}" -> ${l.href}`);
            });

            // Check for 'Adam Young' text to find the container
            const allElements = document.querySelectorAll('*');
            let adamContainer = null;
            for (const el of allElements) {
                if (el.childNodes.length === 1 && el.innerText === 'Adam Young') {
                    adamContainer = el;
                    break;
                }
            }
            if (adamContainer) {
                results.push(`\\nFound 'Adam Young' in: <${adamContainer.tagName} class="${adamContainer.className}">`);
                // Walk up 3 levels
                let parent = adamContainer;
                for (let i = 0; i < 5; i++) {
                    parent = parent.parentElement;
                    if (!parent) break;
                    const childCount = parent.children.length;
                    results.push(`  Parent ${i+1}: <${parent.tagName} class="${parent.className}"> children=${childCount}`);
                }

                // Find the row-like container (the one that repeats)
                let row = adamContainer;
                for (let i = 0; i < 10; i++) {
                    row = row.parentElement;
                    if (!row) break;
                    const siblings = row.parentElement ? row.parentElement.children.length : 0;
                    if (siblings > 3) {
                        results.push(`\\nRow container: <${row.tagName} class="${row.className}">`);
                        results.push(`  Siblings: ${siblings}`);
                        results.push(`  Parent: <${row.parentElement.tagName} class="${row.parentElement.className}">`);
                        // Dump the first row's inner HTML
                        results.push(`\\nFirst row outerHTML (truncated):`);
                        results.push(row.outerHTML.substring(0, 1000));
                        break;
                    }
                }
            } else {
                results.push("\\nCould not find 'Adam Young' text");
                // Dump body structure at top level
                results.push("\\nBody first-level children:");
                for (const child of document.body.children) {
                    results.push(`  <${child.tagName} class="${child.className}" id="${child.id}">`);
                }
            }

            return results.join('\\n');
        }
    """)

    print("\n" + "=" * 60)
    print("DOM INSPECTION RESULTS")
    print("=" * 60)
    print(info)
    print("=" * 60)

    input("\n>>> Press Enter to close... ")
    browser.close()
