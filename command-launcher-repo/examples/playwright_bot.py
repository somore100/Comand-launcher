"""Starter for a Command Vault browser-automation bot.

Add this file as an entry, tick "Persistent browser profile" in the Edit
Entry dialog, and Command Vault passes the profile folder in
COMMAND_VAULT_BROWSER_PROFILE. Log in once with HEADLESS=False (run it by
hand from the entry's Run button); later runs, including scheduled ones,
stay logged in.

Setup:  pip install playwright && playwright install chromium
"""
import os
import sys

from playwright.sync_api import sync_playwright

PROFILE = os.environ.get("COMMAND_VAULT_BROWSER_PROFILE")
HEADLESS = True  # set False for the first run so you can log in by hand

if not PROFILE:
    sys.exit("Tick 'Persistent browser profile' on this entry in Command Vault.")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(PROFILE, headless=HEADLESS)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://example.com")
    print("Title:", page.title())
    # ... your predefined UI path goes here ...
    ctx.close()
