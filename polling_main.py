import os
import threading
from flask import Flask, request
from bot import build_application, load_html_file
from bot import handle_spotify_auth
import logging
from flask import Response
from storage.dynamodb_storage import DynamoDBStorage


webserver = Flask(__name__)

if logging.getLogger().hasHandlers():
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

SPINNER = ["/", "-", "\\", "|"]


@webserver.route("/spotifyauth")
def callback():
    # Handle Spotify OAuth callback
    html_content = load_html_file("index.html")
    code = request.args.get("code")
    state = request.args.get("state")
    logger.info(f"honey we got the code: {code}, and the state: {state}")
    handle_spotify_auth(state, code, storage)
    return Response(html_content, status=200, content_type="text/html")


def run_flask_app():
    webserver.run(host="0.0.0.0", port=8080, debug=True, use_reloader=False)


if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    # Initialize storage
    storage = DynamoDBStorage()

    application = build_application(TOKEN, storage)

    # Start the Flask app in a separate thread
    threading.Thread(target=run_flask_app, daemon=True).start()

    # Start polling
    application.run_polling()
