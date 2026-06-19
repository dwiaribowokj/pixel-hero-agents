"""Playwright capture — proper wait for JS render + animations."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5555/?demo=30"
OUT = sys.argv[2] if len(sys.argv) > 2 else "capture_pw.png"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": 1500, "height": 1200},
        device_scale_factor=1.5,
    )
    page = ctx.new_page()
    page.on("console", lambda msg: print(f"  [console.{msg.type}] {msg.text}"))
    page.on("pageerror", lambda e: print(f"  [PAGE ERROR] {e}"))
    print(f"navigating to {URL}")
    page.goto(URL, wait_until="load", timeout=20000)
    # Wait for first API poll + render + a few sub-roamer movement ticks
    page.wait_for_timeout(5000)
    body_html = page.eval_on_selector("body", "el => el.outerHTML")
    print(f"body length: {len(body_html)}")
    print(f"desks innerHTML length: {page.eval_on_selector('#desks', 'el => el.innerHTML.length')}")
    n = page.eval_on_selector_all(".station", "els => els.length")
    print(f"stations rendered: {n}")
    n_deco = page.eval_on_selector_all(".deco-plant", "els => els.length")
    print(f"deco plants: {n_deco}")
    page.screenshot(path=OUT, full_page=True)
    print(f"saved: {OUT}")
    browser.close()
