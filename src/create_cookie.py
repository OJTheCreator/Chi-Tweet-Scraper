import os
import json

COOKIE_DIR = os.path.join(os.path.dirname(__file__), "..", "cookies")
OUTPUT_FILE = os.path.join(COOKIE_DIR, "twikit_cookies.json")


def convert_editthiscookie_to_twikit_format(raw_cookie_text: str) -> bool:
    """
    Convert raw JSON text from EditThisCookie into
    a Twikit-compatible cookies file saved at cookies/twikit_cookies.json.

    Returns True on success, False otherwise.
    """
    try:
        # Ensure cookies directory exists
        os.makedirs(COOKIE_DIR, exist_ok=True)

        data = json.loads(raw_cookie_text)
        result = {
            item.get("name"): item.get("value")
            for item in data
            if item.get("name") and item.get("value")
        }

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4)

        return True
    except json.JSONDecodeError:
        return False
    except Exception as e:
        print(f"Error saving cookies: {e}")
        return False


if __name__ == "__main__":
    # CLI fallback: prompt user for file path and convert
    path = input("Enter path to your exported EditThisCookie JSON file: ").strip()
    if not os.path.exists(path):
        print(f"File not found: {path}")
        exit(1)

    with open(path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    if convert_editthiscookie_to_twikit_format(raw_text):
        print(f"Cookies saved to {OUTPUT_FILE}")
    else:
        print("Failed to convert cookies. Check JSON format.")
