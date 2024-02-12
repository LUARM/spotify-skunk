import asyncio
import base64
import boto3
import os
import spotipy
import logging
import re
import traceback
import json
from enum import Enum
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
from spotipy.oauth2 import SpotifyOAuth, CacheHandler
from spotipy.exceptions import SpotifyException
import urllib.parse
# user id connected to the channelCredentials info then have it reset when the playlist is reset
# unlink function to remoove their credirtials
# pretty success screem
# reset playlist -> replaceplaylist lets you make a new playlist
# unlink deletes both tables
# update the cache save to acceept user_id for getOauth
# check user_id and see if it machtes the one saved in the table

# fix the path of the first time linking account function


# Load environment variables and configure logging
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


def handle_spotify_auth(event):
    # chat_id = event["queryStringParameters"].get("state")
    state_encoded = event["queryStringParameters"].get("state")
    code = event["queryStringParameters"].get("code")

    if not state_encoded or not code:
        return {"statusCode": 400, "body": "Missing required parameters"}

    # Decoding the state
    state_decoded = urllib.parse.unquote(state_encoded)
    state_info = json.loads(state_decoded)
    chat_id = state_info.get("chat_id")
    user_id = state_info.get("user_id")

    sp_oauth = get_sp_oauth(chat_id, user_id)
    token_info = sp_oauth.get_access_token(code)

    if token_info:
        logger.info(f"Spotify access token successfully retrieved: {token_info}")
    else:
        logger.error("Failed to retrieve Spotify access token")

    return {"statusCode": 200, "body": json.dumps(event, indent=2)}


# -----------------------------------------------
# DynamoDB Utility Functions
# -----------------------------------------------


class BotState(Enum):
    AWAITING_PLAYLIST_IMAGE = "awaiting_playlist_image"
    CHANGING_PLAYLIST_NAME = "changing_playlist_name"
    CREATING_PLAYLIST = "creating_playlist"
    CHANGING_PLAYLIST_IMAGE = "changing_playlist_image"
    NO_STATE = None


dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
bot_table = dynamodb.Table("SpotifySkunk")
credentials_table = dynamodb.Table("ChannelCredentials")


def save_current_state(chat_id, state_key: BotState):
    # Saves the current bot state for a given chat_id in DynamoDB.
    try:
        if state_key is BotState.NO_STATE:
            response = bot_table.update_item(
                Key={"chat_id": str(chat_id)},
                UpdateExpression="REMOVE current_state",
                ReturnValues="UPDATED_NEW",
            )
        else:
            response = bot_table.update_item(
                Key={"chat_id": str(chat_id)},
                UpdateExpression="SET current_state = :state",
                ExpressionAttributeValues={":state": state_key.value},
                ReturnValues="UPDATED_NEW",
            )
        logging.info(f"Updated state in DynamoDB: {response}")
        return response
    except Exception as e:
        logging.error(f"Error saving current state to DynamoDB: {e}")


def get_current_state(chat_id):
    # Retrieves the current bot state for a given chat_id from DynamoDB.
    try:
        response = bot_table.get_item(Key={"chat_id": str(chat_id)})
        if "Item" in response and "current_state" in response["Item"]:
            state_value = response["Item"]["current_state"]
            return BotState(state_value)
        return None
    except Exception as e:
        logging.error(f"Error retrieving current state from DynamoDB: {e}")
        return None


def save_playlist_to_dynamodb(chat_id, playlist_id):
    try:
        bot_table.put_item(Item={"chat_id": str(chat_id), "playlist_id": playlist_id})
    except Exception as e:
        logging.error(f"Error saving to DynamoDB: {e}")


def get_playlist_from_dynamodb(chat_id):
    try:
        response = bot_table.get_item(Key={"chat_id": str(chat_id)})
        if "Item" in response:
            playlist_id = response["Item"].get("playlist_id")
            return playlist_id
        return None
    except Exception as e:
        logging.error(f"Error retrieving from DynamoDB: {e}")
        return None


def get_user_id_from_chat_id(chat_id):
    try:
        response = bot_table.get_item(Key={"chat_id": str(chat_id)})
        if "Item" in response and "user_id" in response["Item"]:
            return response["Item"]["user_id"]
        else:
            logging.info(f"No user_id found for chat_id: {chat_id}")
            return None
    except Exception as e:
        logging.error(
            f"Error retrieving user ID from DynamoDB for chat_id: {chat_id}, error: {e}"
        )
        return None


# Spotify API credentials and initialization
TOKEN = os.getenv("TELERGRAM_BOT_TOKEN")
application = Application.builder().token(TOKEN).build()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")


def get_sp_oauth(chat_id, user_id):
    return SpotifyOAuth(
        SPOTIFY_CLIENT_ID,
        SPOTIFY_CLIENT_SECRET,
        SPOTIFY_REDIRECT_URI,
        cache_handler=DynamoCredentialsCache(chat_id, user_id),
        scope="playlist-modify-public ugc-image-upload",
    )


spotify_link_pattern = r"https://open\.spotify\.com/track/([a-zA-Z0-9]+)"


class DynamoCredentialsCache(CacheHandler):
    """
    A cache handler that stores OAuth credentials in a Dynamo bot_table called
    'ChannelCredentials' that has a primary key of chat_id.
    """

    def __init__(self, chat_id, user_id):
        self.chat_id = chat_id
        self.user_id = user_id

    def get_cached_token(self):
        try:
            response = credentials_table.get_item(Key={"chat_id": str(self.chat_id)})
            if "Item" in response:
                return response["Item"]
            return None
        except Exception as e:
            logging.error(f"Error retrieving from DynamoDB: {e}")
            return None

    def save_token_to_cache(self, token_info):
        try:
            credentials_table.put_item(
                Item={
                    "chat_id": str(self.chat_id),
                    "user_id": self.user_id,
                    **token_info,
                }
            )
            bot_table.update_item(
                Key={"chat_id": str(self.chat_id)},
                UpdateExpression="SET user_id = :uid",
                ExpressionAttributeValues={":uid": str(self.user_id)},
            )
        except Exception as e:
            logging.error(f"Error saving to DynamoDB: {e}")


# -----------------------------------------------
# Spotify Utility Functions
# -----------------------------------------------


def add_track_to_spotify_playlist(playlist_id, track_id, sp_oauth):
    try:
        sp = spotipy.Spotify(auth_manager=sp_oauth)
        sp.playlist_add_items(playlist_id, [f"spotify:track:{track_id}"])
        return True
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 403:
            logging.error("Insufficient client scope for modifying the playlist.")
        else:
            logging.error(f"An error occurred: {e}")
        return False


def change_spotify_playlist_name(playlist_id, new_name, sp_oauth):
    try:
        sp = spotipy.Spotify(auth_manager=sp_oauth)
        sp.playlist_change_details(playlist_id, name=new_name)
        return True
    except SpotifyException as e:
        logging.error(f"Spotify API error in changing playlist name: {e}")
        return False
    except Exception as e:  # Broad catch for debugging
        logging.error(f"Error in changing playlist name: {e}")


def create_spotify_playlist(playlist_name, sp_oauth):
    sp = spotipy.Spotify(auth_manager=sp_oauth)
    user_id = sp.current_user()["id"]
    playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=True)
    return playlist["id"]


async def handle_playlist_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    current_state = get_current_state(chat_id)

    if (
        current_state == BotState.AWAITING_PLAYLIST_IMAGE
        or current_state == BotState.CHANGING_PLAYLIST_IMAGE
    ):
        photo = update.message.photo[-1]
        await update.message.reply_text("Processing your image, please wait...")
        playlist_id = get_playlist_from_dynamodb(chat_id)
        if not playlist_id:
            await update.message.reply_text("No playlist found for this chat.")
            return
        try:
            photo_file = await context.bot.get_file(photo.file_id)
            photo_bytes = await photo_file.download_as_bytearray()
            base64_image = base64.b64encode(photo_bytes).decode("utf-8")

            if len(base64_image) > 256 * 1024:  # 256KB limit
                await update.message.reply_text(
                    "Image is too large. Please use an image less than 256KB."
                )
                return

            async def upload_image():
                sp_oauth = get_sp_oauth(chat_id, user_id)
                sp = spotipy.Spotify(auth_manager=sp_oauth)
                sp.playlist_upload_cover_image(playlist_id, base64_image)

            await asyncio.wait_for(upload_image(), timeout=30)
            await update.message.reply_text("Playlist cover image set successfully!")

            playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
            await update.message.reply_text(
                f"Here's your playlist link: {playlist_url}"
            )

            save_current_state(chat_id, BotState.NO_STATE)
        except asyncio.TimeoutError:
            logging.exception("Error Timeout: TimeoutError")
            await update.message.reply_text("Image upload timed out. Please try again.")
        except Exception as e:
            logging.exception(f"Error uploading playlist image: {e}")
            await update.message.reply_text(f"An error occurred: {e}")
    else:
        await update.message.reply_text(
            "Looks like you are trying to set a image for a nonexistent playlist."
        )


async def handle_playlist_name(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("got to handle_playlist_name")
    chat_id = update.effective_chat.id
    # user_id = update.effective_user.id
    user_id = get_user_id_from_chat_id(chat_id)
    await update.message.reply_text(f"user_id in playlist: {user_id}")
    await update.message.reply_text(f"chat_id: {chat_id}")
    current_state = get_current_state(chat_id)
    sp_oauth = get_sp_oauth(chat_id, user_id)
    await update.message.reply_text(f"current State: {current_state}")

    if current_state == BotState.CHANGING_PLAYLIST_NAME:
        await update.message.reply_text("got to if changing_playlist_name")
        playlist_id = get_playlist_from_dynamodb(chat_id)
        if playlist_id:
            new_name = update.message.text.strip()
            if change_spotify_playlist_name(playlist_id, new_name, sp_oauth):
                await update.message.reply_text(f"Playlist name changed to: {new_name}")
            else:
                await update.message.reply_text(
                    "Failed to change the playlist name. Please try again later."
                )
            save_current_state(chat_id, BotState.NO_STATE)
        else:
            await update.message.reply_text(
                "Make sure you have a playlist created before changing the name."
            )
    elif current_state == BotState.CREATING_PLAYLIST:
        await update.message.reply_text("got to creating_playlist")
        await update.message.reply_text(
            f"create playlist state exists: {current_state}"
        )
        playlist_name = update.message.text.strip()
        try:
            playlist_id = create_spotify_playlist(playlist_name, sp_oauth)
            await update.message.reply_text(f"playlistid: {playlist_id}")
            save_playlist_to_dynamodb(chat_id, playlist_id)
            save_current_state(chat_id, BotState.AWAITING_PLAYLIST_IMAGE)
            await update.message.reply_text(
                f"Created new playlist: {playlist_name}. Now please send me a cool image to set as your playlist cover 😎."
            )
        except Exception as e:
            logging.error(f"Error creating playlist: {e}")
            await update.message.reply_text(
                "Failed to create the playlist. Please try again later."
            )
        return
    else:
        await update.message.reply_text("got to return nada")
        return


async def handle_spotify_links(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text
    match = re.search(spotify_link_pattern, message_text)
    current_state = get_current_state(chat_id)
    if current_state == BotState.CREATING_PLAYLIST:
        await update.message.reply_text(
            "You are in the process of creating a playlist. Please wait until it's done before seding links."
        )
        return
    playlist_id = get_playlist_from_dynamodb(chat_id)
    if match and playlist_id:
        track_id = match.group(1)
        sp_oauth = get_sp_oauth(chat_id, user_id)
        if add_track_to_spotify_playlist(playlist_id, track_id, sp_oauth):
            await update.message.reply_text("Added Spotify track to your playlist!")
            await update.message.reply_text("🦨 ❤️ 🎶")
        else:
            await update.message.reply_text(
                "Failed to add the track. Make sure you have the correct permissions or that the Playlist still exist."
            )
    else:
        await update.message.reply_text(
            "Please create a new playlist using /createplaylist "
        )


# -----------------------------------------------
# Telegram Command Handlers
# -----------------------------------------------


async def change_playlist_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        await update.message.reply_text("Please send the new image for your playlist:")
        save_current_state(chat_id, BotState.CHANGING_PLAYLIST_IMAGE)
    else:
        await update.message.reply_text(
            "No playlist found for this chat. Create one with /createplaylist."
        )


async def change_playlist_name(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        await update.message.reply_text("Please enter the new name for your playlist:")
        save_current_state(chat_id, BotState.CHANGING_PLAYLIST_NAME)
    else:
        await update.message.reply_text(
            "No playlist found for this chat. Create one with /createplaylist."
        )


async def create_playlist(update: Update, context: CallbackContext) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    state_info = {"chat_id": str(chat_id), "user_id": str(user_id)}
    state_encoded = json.dumps(state_info)
    state_url_safe = urllib.parse.quote(state_encoded)

    playlist_id = get_playlist_from_dynamodb(chat_id)

    current_state = get_current_state(chat_id)

    if playlist_id:
        await update.message.reply_text(
            "A playlist has already been created for this chat."
        )
        return False

    if current_state == BotState.CREATING_PLAYLIST:
        await update.message.reply_text(
            "You are already in the process of creating a playlist."
        )
        return False

    save_current_state(chat_id, BotState.CREATING_PLAYLIST)
    sp_oauth = get_sp_oauth(chat_id, user_id)
    tokinfo = sp_oauth.cache_handler.get_cached_token()
    if sp_oauth.validate_token(tokinfo) is None:
        auth_url = sp_oauth.get_authorize_url(state=state_url_safe)
        await update.message.reply_text(f"click this:{auth_url}")
    else:
        await update.message.reply_text("Please enter a name for your new playlist:")
    return True


async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "Here are the commands you can use:\n"
        "/start - Start interacting with the bot\n"
        "/createplaylist - Create a new Spotify playlist\n"
        "/changeplaylistname - Change the name of the current playlist\n"
        "/changeplaylistimage - Change the image of the current playlist\n"
        "/resetplaylist - Reset so you can create a new playlist\n"
        "/unlink - Unlink your Spotify credentials\n"
        "/playlistlink - Get the link to the current playlist\n"
        "/help - Show this help message\n"
        "\nJust send me a Spotify track link to add it to your playlist!"
    )
    await update.message.reply_text(help_text)


async def reset_playlist(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    # Delete the playlist entry from DynamoDB
    try:
        bot_table.delete_item(Key={"chat_id": str(chat_id)})
    except Exception as e:
        logging.error(f"Error deleting from DynamoDB: {e}")
        await update.message.reply_text("Failed to reset the playlist in the database.")
        return
    await update.message.reply_text(
        "The current playlist has been reset. You can create a new playlist with /createplaylist."
    )


async def send_playlist_link(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        await update.message.reply_text(f"Here's your playlist link: {playlist_url}")
    else:
        await update.message.reply_text("No playlist found for this chat.")


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "Hiya! I'm your Spotify Skunk bot 🦨. /createplaylist so I can add spotify links as tracks in your playlist! "
    )


async def unlink_credentials(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    try:
        credentials_table.delete_item(Key={"chat_id": str(chat_id)})
        bot_table.delete_item(Key={"chat_id": str(chat_id)})
        await update.message.reply_text(
            "Your Spotify credentials have been unlinked successfully."
        )
    except Exception as e:
        logger.error(f"Error unlinking Spotify credentials for chat_id {chat_id}: {e}")
        await update.message.reply_text(
            "Failed to unlink your Spotify credentials. Please try again later."
        )


async def main(event, context):
    # Define and add handlers
    handlers = [
        CommandHandler("start", start),
        CommandHandler("help", help_command),
        CommandHandler("createplaylist", create_playlist),
        CommandHandler("resetplaylist", reset_playlist),
        CommandHandler("changeplaylistname", change_playlist_name),
        CommandHandler("changeplaylistimage", change_playlist_image),
        CommandHandler("playlistlink", send_playlist_link),
        CommandHandler("unlink", unlink_credentials),
        MessageHandler(
            filters.TEXT & filters.Regex(spotify_link_pattern), handle_spotify_links
        ),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_playlist_name),
        MessageHandler(filters.PHOTO, handle_playlist_image),
    ]

    for handler in handlers:
        application.add_handler(handler)

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
