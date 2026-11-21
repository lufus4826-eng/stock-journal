"""
Streamlit Keep-Alive Script
Automates visiting deployed Streamlit apps using Playwright (Chromium)
to prevent Streamlit Community Cloud apps from entering inactivity hibernation (sleep mode).
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

# In the public repository, only ping the public showcase demo URL
URLS = [
    os.getenv("STREAMLIT_APP_URL", "https://stock-journal-4i7wnvrpwpnwdrck6vbm98.streamlit.app/")
]

def ping_apps():
    print("=" * 60)
    print("🚀 STARTING STREAMLIT KEEP-ALIVE PING")
    print("=" * 60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for url in URLS:
            print(f"\n[TARGET] Navigating to: {url}")
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(8)

                title = page.title()
                print(f"         Page Title: {title}")

                wake_selectors = [
                    "button:has-text('get this app back up')",
                    "button:has-text('wake up')",
                    "button:has-text('Yes, get this app back up')",
                    "button:has-text('Wake back up')"
                ]

                button_clicked = False
                for sel in wake_selectors:
                    btn = page.locator(sel)
                    if btn.count() > 0:
                        print(f"         ⚠️ App is asleep! Found wake button matching: '{sel}'")
                        btn.first.click()
                        time.sleep(15)
                        button_clicked = True
                        print("         ✅ Clicked wake-up button! App container is booting up.")
                        break

                if not button_clicked:
                    print("         ✅ App is active and responsive (No wake button needed).")

            except Exception as e:
                print(f"         ⚠️ Notice while pinging {url}: {e}")

        browser.close()

    print("\n" + "=" * 60)
    print("🎉 KEEP-ALIVE ROUTINE COMPLETED SUCCESSFULLY")
    print("=" * 60)

if __name__ == "__main__":
    ping_apps()
