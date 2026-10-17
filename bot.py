import json
import os
import requests
from pathlib import Path

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
X_USERNAME = os.environ["X_USERNAME"].lstrip("@")

STATE_FILE = Path("last_tweet.json")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
FX_API = f"https://api.fxtwitter.com/2/profile/{X_USERNAME}/statuses"


def get_latest_posts():
    r = requests.get(
        FX_API,
        params={"limit": 10},
        headers={"User-Agent": "alice-x-telegram/1.0"},
        timeout=30,
    )
    r.raise_for_status()

    data = r.json()

    # FxTwitter timeline endpoints normally expose posts as results.
    posts = data.get("results", [])

    if not posts:
        print("No posts returned.")
        return []

    return posts


def load_last_id():
    if not STATE_FILE.exists():
        return None

    try:
        return json.loads(STATE_FILE.read_text()).get("last_id")
    except Exception:
        return None


def save_last_id(tweet_id):
    STATE_FILE.write_text(
        json.dumps({"last_id": str(tweet_id)}, indent=2)
    )


def tg(method, payload=None):
    r = requests.post(
        f"{TG_API}/{method}",
        json=payload or {},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def send_text(text):
    tg(
        "sendMessage",
        {
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
    )


def send_photo(url, caption=""):
    tg(
        "sendPhoto",
        {
            "chat_id": CHAT_ID,
            "photo": url,
            "caption": caption[:1024],
        },
    )


def send_media_group(media, caption=""):
    items = []

    for index, item in enumerate(media[:10]):
        items.append(
            {
                "type": "photo",
                "media": item["url"],
                "caption": caption[:1024] if index == 0 else "",
            }
        )

    tg(
        "sendMediaGroup",
        {
            "chat_id": CHAT_ID,
            "media": items,
        },
    )


def send_video(url, caption=""):
    tg(
        "sendVideo",
        {
            "chat_id": CHAT_ID,
            "video": url,
            "caption": caption[:1024],
            "supports_streaming": True,
        },
    )


def send_post(post):
    tweet_id = str(post["id"])
    text = post.get("text", "").strip()

    author = post.get("author") or {}
    name = author.get("name", X_USERNAME)
    handle = author.get("screen_name", X_USERNAME)

    tweet_url = post.get("url") or (
        f"https://x.com/{handle}/status/{tweet_id}"
    )

    caption = f"{name} (@{handle})\n\n{text}\n\n🔗 {tweet_url}"

    media = post.get("media") or {}
    photos = media.get("photos") or []
    videos = media.get("videos") or []

    if photos:
        if len(photos) == 1:
            send_photo(photos[0]["url"], caption)
        else:
            send_media_group(photos, caption)

    elif videos:
        video = videos[0]
        video_url = video.get("url") or video.get("transcode_url")

        if video_url:
            send_video(video_url, caption)
        else:
            send_text(caption)

    else:
        send_text(caption)


def main():
    posts = get_latest_posts()

    if not posts:
        return

    # Highest Snowflake ID = newest post.
    posts = sorted(posts, key=lambda p: int(p["id"]))

    last_id = load_last_id()

    # First run:
    # save the newest existing post without forwarding old tweets.
    if last_id is None:
        newest = posts[-1]["id"]
        save_last_id(newest)
        print(f"Initialized at tweet {newest}.")
        return

    new_posts = [
        post
        for post in posts
        if int(post["id"]) > int(last_id)
    ]

    if not new_posts:
        print("No new posts.")
        return

    for post in new_posts:
        send_post(post)
        save_last_id(post["id"])
        print(f"Sent {post['id']}")


if __name__ == "__main__":
    main()
