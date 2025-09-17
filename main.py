import os
import time

from fastapi import FastAPI, Request, status, HTTPException, Response
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from utils import (
    send_text,
    ask_story_consent,
    send_image,
    list_images_from_manifest,
    make_story_from_urls,
    upload_story_to_s3,
    get_username,
    upload_story_with_tag,
)

load_dotenv()

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")


@app.get("/")
async def read_root(request: Request):
    return "hello"


@app.get("/instagram")
async def instagram_webhook(request: Request):
    hub_mode = request.query_params.get("hub.mode")
    hub_challenge = request.query_params.get("hub.challenge")
    hub_token = request.query_params.get("hub.verify_token")

    req = {"mode": hub_mode, "challenge": hub_challenge, "token": hub_token}

    print(req)

    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        print("we're returing challenge ", hub_challenge)
        return PlainTextResponse(hub_challenge, status_code=200)
    else:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST)


@app.post("/instagram")
async def instagram_webhook(request: Request):
    body = await request.json()

    try:
        print("body", body)
        sender_id = body["entry"][0]["messaging"][0]["sender"]["id"]
        text = body["entry"][0]["messaging"][0]["message"]["text"]
        quick_reply = body["entry"][0]["messaging"][0]["message"].get("quick_reply")

        if not quick_reply and text[0] == "#" and len(text) == 5:
            # c5T8Mh
            code = text[1:]

            image_urls = list_images_from_manifest(code)

            if not image_urls:
                send_text(sender_id, "გალერეის კოდი არასწორია, თავიდან სცადეთ")

                raise Exception("Wrong gallery code")

            link = f"https://funwell-gallery-bucket.s3.amazonaws.com/gallery/{code}/index.html"

            send_text(sender_id, link)
            # send_text(sender_id, "დაელოდეთ, თქვენი სთორი გენერირდება...")
            # time.sleep(0.3)

            # story_img = make_story_from_urls(image_urls[1:])

            # story_url = upload_story_to_s3(story_img, code)

            # send_image(
            #     sender_id,
            #     story_url,
            # )

            # time.sleep(0.3)

            # ask_story_consent(sender_id, story_url)

        elif quick_reply:
            payload = quick_reply["payload"]

            action, sender_id, story_url = payload.split(" ")

            print("got values: ", action, sender_id, story_url)

            if action == "yes":

                username = get_username(sender_id)

                send_text(sender_id, "თქვენი სთორი აიტვირთა ❤️")

                upload_story_with_tag(story_url, username)

                print("WE ARE UPLOADING THE STORY")
            elif action == "no":
                print("WE ARE NOT UPLOADING")

    except Exception as e:
        print("ERROR Something went wrong: ", e)

        return Response(status_code=status.HTTP_200_OK)

    return Response(status_code=status.HTTP_200_OK)
