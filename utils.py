import os, io, time, json
from datetime import datetime

import requests
from dotenv import load_dotenv
from PIL import Image
import boto3

load_dotenv()

INSTA_ACCESS_TOKEN = os.getenv("INSTA_ACCESS_TOKEN")
FUNWELL_ACCOUNT_ID = os.getenv("FUNWELL_ACCOUNT_ID")

INSTAGRAM_GRAPH_URL = f"https://graph.instagram.com/v23.0"

SEND_API_URL = f"{INSTAGRAM_GRAPH_URL}/{FUNWELL_ACCOUNT_ID}/messages"


def send_text(recipient_id: str, text: str):
    headers = {"Authorization": f"Bearer {INSTA_ACCESS_TOKEN}"}
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}

    r = requests.post(SEND_API_URL, headers=headers, json=payload)
    r.raise_for_status()


def send_image(recipient_id: str, image_url: str):
    headers = {"Authorization": f"Bearer {INSTA_ACCESS_TOKEN}"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {
                    "url": image_url,
                },
            }
        },
    }

    r = requests.post(SEND_API_URL, headers=headers, json=payload)
    print(r.json())
    r.raise_for_status()


def ask_story_consent(recipient_id: str, story_url):
    headers = {"Authorization": f"Bearer {INSTA_ACCESS_TOKEN}"}

            # "text": "გინდათ ეს ფოტო დავსთოროთ?",
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {
            "text": "Do you want us to upload this story and mention you?",
            "quick_replies": [
                {
                    "content_type": "text",
                    "title": "Yes",
                    "payload": f"yes {recipient_id} {story_url}",
                },
                {
                    "content_type": "text",
                    "title": "No",
                    "payload": f"no {recipient_id} {story_url}",
                },
            ],
        },
    }

    r = requests.post(SEND_API_URL, headers=headers, json=payload)
    r.raise_for_status()


def list_images_from_manifest(code: str) -> list[str]:
    try:
        url = f"https://funwell-gallery-bucket.s3.amazonaws.com/gallery/{code}/manifest.json"
        r = requests.get(url, timeout=10)
        r.raise_for_status()

    except Exception:
        return False

    data = r.json()
    return [
        f"https://funwell-gallery-bucket.s3.amazonaws.com/gallery/{code}/{name}"
        for name in data.get("images", [])
    ]


def fetch_image(url: str) -> Image.Image:
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGBA")


def make_story_from_urls(urls: list[str]) -> Image.Image:
    STORY_W, STORY_H = 1080, 1920

    imgs = []

    for u in urls:
        try:
            im = fetch_image(u)  # from snippet A
        except Exception:
            continue
        # fit to width
        w_percent = STORY_W / im.width
        new_size = (STORY_W, int(im.height * w_percent))
        im = im.resize(new_size, Image.LANCZOS).convert("RGB")
        imgs.append(im)

    if not imgs:
        raise RuntimeError("No images fetched")

    # stack vertically
    total_h = sum(im.height for im in imgs)
    stacked = Image.new("RGB", (STORY_W, total_h), (0, 0, 0))
    y = 0
    for im in imgs:
        stacked.paste(im, (0, y))
        y += im.height

    # Center-crop (or pad) to 1080x1920
    if total_h >= STORY_H:
        top = (total_h - STORY_H) // 2
        story = stacked.crop((0, top, STORY_W, top + STORY_H))
    else:
        # not tall enough; pad top/bottom
        story = Image.new("RGB", (STORY_W, STORY_H), (0, 0, 0))
        top = (STORY_H - total_h) // 2
        story.paste(stacked, (0, top))

    story.save(f"story{int(time.time())}.jpg")

    return story


def upload_story_to_s3(story_img, code: str):
    s3 = boto3.client("s3")
    bucket = "funwell-gallery-bucket"

    buffer = io.BytesIO()
    story_img.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    story_name = f"{code}_{timestamp}.jpg"

    s3.put_object(
        Bucket=bucket,
        Key=f"story/{story_name}",
        Body=buffer,
        ContentType="image/jpeg",
    )

    return f"https://{bucket}.s3.amazonaws.com/story/{story_name}"


def get_username(sender_id):
    url = f"{INSTAGRAM_GRAPH_URL}/{sender_id}"
    params = {
        "fields": "username",
        "access_token": INSTA_ACCESS_TOKEN,
    }

    r = requests.get(url, params=params)
    r.raise_for_status()

    return r.json().get("username")


def upload_story_with_tag(image_url: str, tagged_username: str):
    url = f"{INSTAGRAM_GRAPH_URL}/{FUNWELL_ACCOUNT_ID}/media"
    params = {
        "media_type": "STORIES",
        "image_url": image_url,
        "user_tags": json.dumps([{"username": tagged_username}]),
        "access_token": INSTA_ACCESS_TOKEN,
    }

    r = requests.post(url, params=params)
    r.raise_for_status()
    print(r.json())
    creation_id = r.json()["id"]

    publish_url = f"{INSTAGRAM_GRAPH_URL}/{FUNWELL_ACCOUNT_ID}/media_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": INSTA_ACCESS_TOKEN,
    }

    r2 = requests.post(publish_url, json=publish_payload)
    r2.raise_for_status()
    print(r2.json())

    return r2.json()
