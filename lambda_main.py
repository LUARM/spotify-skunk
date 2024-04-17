import asyncio
from bot import handle_spotify_auth, load_html_file
import logging
from bot import build_application
import os
import json
import traceback
from telegram import Update

if logging.getLogger().hasHandlers():
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def lambda_handler(event, context):
    logger.info(f"Event body type: {type(event)}")
    logger.info(f"Event body content: {event}")
    if event.get("body"):
        # I'm a telegram bot post webhook served via the API GAteway.
        return asyncio.get_event_loop().run_until_complete(main(event, context))
    elif event.get("rawPath") == "/spotifyauth":
        # This is served by the Lambda Function URL.
        # Spotify API refers to this as the redirect URI and it is also the path
        # you've specified in your Spotify Developer Dashboard.
        return handle_spotify_auth(event)
    else:
        return {"statusCode": 404, "body": "no handler for this request"}


def handle_spotify_event(event):
    html_content = load_html_file("index.html")
    state_encoded = event["queryStringParameters"].get("state")
    code = event["queryStringParameters"].get("code")

    if not state_encoded or not code:
        return {"statusCode": 400, "body": "Missing required parameters"}
    handle_spotify_auth(state_encoded, code)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": html_content,
    }


async def main(event, context):
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    application = build_application(TOKEN)

    # Convert the incoming event to a Telegram Update object
    if isinstance(event["body"], str):
        body = json.loads(event["body"])
    else:
        body = event["body"]

    try:
        await application.initialize()
        await application.process_update(Update.de_json(body, application.bot))
        return {"statusCode": 200, "body": json.dumps("Success")}
    except Exception:
        logger.exception("Error processing update")
        return {
            "statusCode": 500,
            "body": f"Error processing update: {traceback.format_exc()}",
        }


if __name__ == "__main__":
    main()
