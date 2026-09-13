"""Open ChatGPT in a visible, user-controlled Playwright browser."""

from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".secrets" / "chatgpt-browser-profile"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Install the optional launcher first: .\\.venv\\Scripts\\python.exe -m pip install -e ".[chatgpt-ui]"',
              file=sys.stderr)
        return 1

    PROFILE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        # Use the installed Chrome browser. The profile stays local and is
        # ignored by Git; this script never reads or exports its contents.
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), channel="chrome", headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
        print("ChatGPT opened. Sign in and use the page manually. Press Ctrl+C here to close the browser.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nClosing ChatGPT browser.")
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
