import json
import os
import requests
from pathlib import Path

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
THREAD_ID = int(os.environ["TELEGRAM_THREAD_ID"])

ALICE_X_USERNAME = os.environ["X_USERNAME"].lstrip("@")
KIXLY_X_USERNAME = os.environ["KIXLY_X_USERNAME"].lstrip("@")
X_USERNAMES = [ALICE_X_USERNAME, KIXLY_X_USERNAME]

STATE_FILE = Path("last_tweet.json")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def get_latest_posts(username):
    fx_api = f"https://api.fxtwitter.com/2/profile/{username}/statuses"

    r = requests.get(
        fx_api,
        params={"limit": 10},
        headers={"User-Agent": "alice-x-telegram/1.0"},
        timeout=30,
    )
    r.raise_for_status()

    data = r.json()
    posts = data.get("results", [])

    if not posts:
        print(f"No posts returned for @{username}.")
        return []

    return posts


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        data = json.loads(STATE_FILE.read_text())

        # Backward compatibility with the old single-account format:
        # {"last_id": "..."}
        if "last_id" in data:
            return {ALICE_X_USERNAME: str(data["last_id"])}

        return {
            username: str(tweet_id)
            for username, tweet_id in data.items()
            if tweet_id is not None
        }
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, indent=2, sort_keys=True)
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
            "message_thread_id": THREAD_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
    )


def send_photo(url, caption=""):
    tg(
        "sendPhoto",
        {
            "chat_id": CHAT_ID,
            "message_thread_id": THREAD_ID,
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
            "message_thread_id": THREAD_ID,
            "media": items,
        },
    )


def send_video(url, caption=""):
    tg(
        "sendVideo",
        {
            "chat_id": CHAT_ID,
            "message_thread_id": THREAD_ID,
            "video": url,
            "caption": caption[:1024],
            "supports_streaming": True,
        },
    )


def send_post(post, fallback_username):
    tweet_id = str(post["id"])
    text = post.get("text", "").strip()

    author = post.get("author") or {}
    name = author.get("name", fallback_username)
    handle = author.get("screen_name", fallback_username)

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


def process_account(username, state):
    posts = get_latest_posts(username)

    if not posts:
        return

    # Highest Snowflake ID = newest post.
    posts = sorted(posts, key=lambda p: int(p["id"]))
    last_id = state.get(username)

    # First run for this account:
    # save the newest existing post without forwarding old posts.
    if last_id is None:
        newest = str(posts[-1]["id"])
        state[username] = newest
        save_state(state)
        print(f"Initialized @{username} at post {newest}.")
        return

    new_posts = [
        post
        for post in posts
        if int(post["id"]) > int(last_id)
    ]

    if not new_posts:
        print(f"No new posts for @{username}.")
        return

    for post in new_posts:
        send_post(post, username)
        state[username] = str(post["id"])
        save_state(state)
        print(f"Sent @{username} post {post['id']}")


def main():
    state = load_state()
    errors = []

    for username in X_USERNAMES:
        try:
            process_account(username, state)
        except Exception as exc:
            # Keep processing the other account. The workflow will still persist
            # any state changes from posts that were already sent successfully.
            print(f"ERROR processing @{username}: {exc}")
            errors.append((username, exc))

    if errors:
        failed = ", ".join(f"@{username}" for username, _ in errors)
        raise RuntimeError(f"Sync failed for: {failed}")


if __name__ == "__main__":
    main()
