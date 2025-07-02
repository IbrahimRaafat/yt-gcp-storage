import subprocess
import yt_dlp
from titleGetter import getTitle
import os

url = "https://www.youtube.com/watch?v=Ajz6dBp_EB4"  # Replace with actual URL


def get_480p_filename(url):
    title = getTitle(url)
    # yt-dlp replaces some characters in the title for filenames, so we should sanitize
    # We'll mimic yt-dlp's default sanitization for basic cases
    safe_title = "".join(c for c in title if c not in '\\/:*?\"<>|').strip()
    return f"{safe_title}_480p.mp4"  # assuming mp4 is the most common


def sanitize_title(title):
    # Remove forbidden filename characters
    return "".join(c for c in title if c not in '\\/:*?"<>|').strip()


def download480(url):
    title = getTitle(url)
    safe_title = "".join(c for c in title if c not in '\\/:*?"<>|').strip()
    base_filename = f"{safe_title}_480p"
    try:
        # Download with yt-dlp
        subprocess.run([
            "yt-dlp",
            "-f", "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "--cookies", "cookies.txt",
            "-o", base_filename + ".%(ext)s",
            url,
        ], check=True)
        # Check for possible extensions
        for ext in ["mp4", "webm", "mkv"]:
            candidate = f"{base_filename}.{ext}"
            if os.path.exists(candidate):
                return candidate
        return None
    except Exception as e:
        print(f"Download failed: {e}")
        return None

