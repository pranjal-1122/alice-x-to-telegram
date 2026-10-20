import os
import requests

from bot import send_post

TWEET_ID = os.environ["TWEET_ID"].strip()

if not TWEET_ID.isdigit():
    raise ValueError("TWEET_ID must contain only digits.")

url = f"https://api.fxtwitter.com/2/status/{TWEET_ID}"

r = requests.get(
    url,
    headers={"User-Agent": "alice-x-telegram/1.0"},
    timeout=30,
)
r.raise_for_status()

data = r.json()
post = data.get("status")

if not post or post.get("type") != "status":
    raise RuntimeError(f"Could not fetch X post {TWEET_ID}.")

author = post.get("author") or {}
fallback_username = author.get("screen_name", "X")

send_post(post, fallback_username)
print(f"Manually posted X status {TWEET_ID} to Telegram.")
