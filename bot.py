import asyncio
import base64
import os
import spotipy
import logging
import re
import json
import telegram
from telegram import Update, LinkPreviewOptions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    Defaults,
    ContextTypes,
)
from spotipy.oauth2 import SpotifyOAuth, CacheHandler
from spotipy.exceptions import SpotifyException
import urllib.parse
from custom_callback_contex import CustomCallbackContext
from storage.storage_interface import BotState

if logging.getLogger().hasHandlers():
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# Constants and configurations
defaults = Defaults(
    link_preview_options=LinkPreviewOptions(show_above_text=False, is_disabled=True),
    disable_notification=True,
)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
spotify_link_pattern = r"https://open\.spotify\.com/track/([a-zA-Z0-9]+)"


def load_html_file(file_name):
    with open(os.path.join("html", file_name), encoding="utf-8") as file:
        return file.read()


def handle_spotify_auth(state, code, storage):
    state_decoded = urllib.parse.unquote(state)
    state_info = json.loads(state_decoded)
    chat_id = state_info.get("chat_id")
    user_id = state_info.get("user_id")

    sp_oauth = get_sp_oauth(chat_id, user_id, storage)
    token_info = sp_oauth.get_access_token(code)

    if token_info:
        TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        bot = telegram.Bot(TOKEN)
        logger.info(f"Spotify access token successfully retrieved: {token_info}")
        asyncio.run(
            bot.send_message(text="Enter a name for your new playlist", chat_id=chat_id)
        )
    else:
        logger.error("Failed to retrieve Spotify access token")
    # For logging:
    # return {"statusCode": 200, "body": json.dumps(event, indent=2)}


class DynamoCredentialsCache(CacheHandler):
    """
    A cache handler that stores OAuth credentials in a Dynamo bot_table called
    'ChannelCredentials' that has a primary key of chat_id.
    """

    def __init__(self, chat_id, user_id, storage):
        self.chat_id = chat_id
        self.user_id = user_id
        self.storage = storage

    def get_cached_token(self):
        try:
            return self.storage.get_cached_token(self.chat_id)
        except Exception as e:
            logging.error(f"Error retrieving cached token from DynamoDB: {e}")
            raise

    def save_token_to_cache(self, token_info):
        try:
            self.storage.save_token_to_cache(self.chat_id, self.user_id, token_info)
        except Exception as e:
            logging.error(f"Error saving token to DynamoDB: {e}")
            raise


# -----------------------------------------------
# Spotify Utility Functions
# -----------------------------------------------
def get_sp_oauth(chat_id, user_id, storage):
    # TODO: Pass Storage Param
    return SpotifyOAuth(
        SPOTIFY_CLIENT_ID,
        SPOTIFY_CLIENT_SECRET,
        SPOTIFY_REDIRECT_URI,
        cache_handler=DynamoCredentialsCache(chat_id, user_id, storage),
        scope="playlist-modify-public ugc-image-upload",
    )


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
    except Exception as e:
        logging.error(f"Error in changing playlist name: {e}")


def create_spotify_playlist(playlist_name, sp_oauth):
    sp = spotipy.Spotify(auth_manager=sp_oauth)
    user_id = sp.current_user()["id"]
    playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=True)
    return playlist["id"]


# -----------------------------------------------
# Telegram Message Handlers
# -----------------------------------------------
async def handle_playlist_image(update: Update, context: CustomCallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_id_table = context.storage().get_user_id_from_chat_id(chat_id)
    if user_id_table != str(user_id):
        await update.message.reply_text(
            "You are not authorized for this playlist process."
        )
        return
    current_state = context.storage().get_current_state(chat_id)
    if (
        current_state == BotState.AWAITING_PLAYLIST_IMAGE
        or current_state == BotState.CHANGING_PLAYLIST_IMAGE
    ):
        photo = update.message.photo[-1]
        await update.message.reply_text("Processing your image, please wait...")
        playlist_id = context.storage().get_playlist_from_dynamodb(chat_id)
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
                sp_oauth = get_sp_oauth(chat_id, user_id, context.storage())
                sp = spotipy.Spotify(auth_manager=sp_oauth)
                sp.playlist_upload_cover_image(playlist_id, base64_image)

            await asyncio.wait_for(upload_image(), timeout=30)
            await update.message.reply_text("Playlist cover image set successfully!")

            playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
            await update.message.reply_text(
                f"Here's your playlist link: {playlist_url}",
                disable_web_page_preview=False,
                link_preview_options=LinkPreviewOptions(
                    show_above_text=True, is_disabled=False
                ),
            )

            context.storage().save_current_state(chat_id, BotState.NO_STATE)
        except asyncio.TimeoutError:
            logging.exception("Error Timeout: TimeoutError")
            await update.message.reply_text("Image upload timed out. Please try again.")
        except Exception as e:
            logging.exception(f"Error uploading playlist image: {e}")
            await update.message.reply_text(f"An error occurred: {e}")


async def handle_playlist_name(update: Update, context: CustomCallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_id_bot_table = context.storage().get_user_id_from_chat_id(chat_id)
    user_id_credentials_table = context.storage().get_user_id_from_channel_credentials(
        chat_id
    )
    logger.info(f"user id table: {user_id_credentials_table}, user id: {user_id} ")

    current_state = context.storage().get_current_state(chat_id)
    logging.info(f"the state here-pre is: {current_state}, {type(current_state)}")
    sp_oauth = get_sp_oauth(chat_id, user_id, context.storage())
    logging.info(f"here is sp oauth: {sp_oauth}")

    if current_state == BotState.CHANGING_PLAYLIST_NAME:
        if user_id_bot_table != str(user_id):
            await update.message.reply_text(
                "Please click on authorize link before entering playlist name."
            )
            return
        playlist_id = context.storage().get_playlist_from_dynamodb(chat_id)
        if playlist_id:
            new_name = update.message.text.strip()
            if change_spotify_playlist_name(playlist_id, new_name, sp_oauth):
                await update.message.reply_text(f"Playlist name changed to: {new_name}")
            else:
                await update.message.reply_text(
                    "Failed to change the playlist name. Please try again later."
                )
            context.storage().save_current_state(chat_id, BotState.NO_STATE)
        else:
            await update.message.reply_text(
                "Make sure you have a playlist created before changing the name."
            )
    elif current_state is BotState.CREATING_PLAYLIST:
        logging.info(f"the state here is: {current_state}")
        if str(user_id) != user_id_credentials_table:
            await update.message.reply_text(
                "You are not authorized for this playlist process."
            )
            return

        playlist_name = update.message.text.strip()
        try:
            playlist_id = create_spotify_playlist(playlist_name, sp_oauth)
            context.storage().save_playlist_to_dynamodb(chat_id, playlist_id)
            context.storage().save_current_state(
                chat_id, BotState.AWAITING_PLAYLIST_IMAGE
            )
            await update.message.reply_text(
                f"Created new playlist: {playlist_name}. "
                "Now please send me a cool image to set as your playlist cover 😎."
            )
        except Exception as e:
            logging.error(f"Error creating playlist: {e}")
            await update.message.reply_text(
                "Failed to create the playlist. Please try again later."
            )
        return
    else:
        return


async def handle_spotify_links(update: Update, context: CustomCallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text
    match = re.search(spotify_link_pattern, message_text)
    current_state = context.storage().get_current_state(chat_id)
    if current_state == BotState.CREATING_PLAYLIST:
        await update.message.reply_text(
            "You are in the process of creating a playlist. "
            "Please wait until it's done before sending links."
        )
        return
    playlist_id = context.storage().get_playlist_from_dynamodb(chat_id)
    if match and playlist_id:
        track_id = match.group(1)
        sp_oauth = get_sp_oauth(chat_id, user_id, context.storage())
        if add_track_to_spotify_playlist(playlist_id, track_id, sp_oauth):
            await update.message.set_reaction("👍")
        else:
            await update.message.reply_text(
                "Failed to add the track. Make sure you have the correct permissions "
                "or that the Playlist still exist."
            )
    else:
        await update.message.reply_text(
            "Please create a new playlist using /createplaylist "
        )


# -----------------------------------------------
# Telegram Command Handlers
# -----------------------------------------------
async def change_playlist_image(update: Update, context: CustomCallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = context.storage().get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        await update.message.reply_text("Please send the new image for your playlist:")
        context.storage().save_current_state(chat_id, BotState.CHANGING_PLAYLIST_IMAGE)
    else:
        await update.message.reply_text(
            "No playlist found for this chat. Create one with /createplaylist."
        )


async def change_playlist_name(update: Update, context: CustomCallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = context.storage().get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        await update.message.reply_text("Please enter the new name for your playlist:")
        context.storage().save_current_state(chat_id, BotState.CHANGING_PLAYLIST_NAME)
    else:
        await update.message.reply_text(
            "No playlist found for this chat. Create one with /createplaylist."
        )


async def create_playlist(update: Update, context: CustomCallbackContext) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    state_info = {"chat_id": str(chat_id), "user_id": str(user_id)}
    state_encoded = json.dumps(state_info)
    state_url_safe = urllib.parse.quote(state_encoded)

    playlist_id = context.storage().get_playlist_from_dynamodb(chat_id)

    current_state = context.storage().get_current_state(chat_id)

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
    context.storage().save_current_state(chat_id, BotState.CREATING_PLAYLIST)
    sp_oauth = get_sp_oauth(chat_id, user_id, context.storage())
    token_info = sp_oauth.cache_handler.get_cached_token()
    if sp_oauth.validate_token(token_info) is None:
        auth_url = sp_oauth.get_authorize_url(state=state_url_safe)
        await update.message.reply_text(
            f"click this to authorize the bot:{auth_url}", protect_content=True
        )
    else:
        await update.message.reply_text("Please enter a name for your new playlist:")
    return True


async def help_command(update: Update, context: CustomCallbackContext) -> None:
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


async def reset_playlist(update: Update, context: CustomCallbackContext) -> None:
    chat_id = update.effective_chat.id
    # Delete the playlist entry from DynamoDB
    try:
        context.storage().delete_item(context.storage().bot_table, chat_id)
    except Exception:
        await update.message.reply_text("Failed to reset the playlist in the database.")
        return
    await update.message.reply_text(
        "The current playlist has been reset. "
        "You can create a new playlist with /createplaylist."
    )


async def send_playlist_link(update: Update, context: CustomCallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = context.storage().get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        await update.message.reply_text(
            f"Here's your playlist link: {playlist_url}",
            disable_web_page_preview=False,
            link_preview_options=LinkPreviewOptions(
                show_above_text=True, is_disabled=False
            ),
        )
    else:
        await update.message.reply_text("No playlist found for this chat.")


async def start(update: Update, context: CustomCallbackContext) -> None:
    await update.message.reply_text(
        "Hiya! I'm your Spotify Skunk bot 🦨. /createplaylist "
        "to add songs to your playlist!"
    )


async def unlink_credentials(update: Update, context: CustomCallbackContext) -> None:
    chat_id = update.effective_chat.id
    try:
        # Check if the item exists in the credentials table
        if not context.storage().check_item_exists(
            "credentials_table", chat_id
        ):
            logging.error(f"Credentials not found for chat_id {chat_id}")
            await update.message.reply_text(
                "Failed to unlink your Spotify credentials: credentials not found."
            )
            return

        # Check if the item exists in the bot table

        if not context.storage().check_item_exists(
            "bot_table", chat_id
        ):
            logging.error(f"Bot data not found for chat_id {chat_id}")
            await update.message.reply_text(
                "Failed to unlink your Spotify credentials: bot data not found."
            )
            return

        # Log the deletion attempt
        logging.info(
            f"Attempting to delete item from credentials table for chat_id {chat_id}"
        )
        credentials_delete_response = context.storage().delete_item(
            "credentials_table", chat_id
        )
        logging.info(f"Credentials delete_item response: {credentials_delete_response}")

        logging.info(f"Attempting to delete item from bot table for chat_id {chat_id}")
        bot_delete_response = context.storage().delete_item(
            "bot_table", chat_id
        )
        logging.info(f"Bot delete_item response: {bot_delete_response}")

        await update.message.reply_text(
            "Your Spotify credentials have been unlinked successfully."
        )
    except Exception as e:
        logger.error(f"Error unlinking Spotify credentials for chat_id {chat_id}: {e}")
        await update.message.reply_text(
            "Failed to unlink your Spotify credentials. Please try again later."
        )


# TODO: Fix so it Only Works for You and in Group Chats
async def debug_stuff(update: Update, context: CustomCallbackContext):
    chat_id = update.effective_chat.id
    debug = "\n".join(
        [
            f"Owning User ID: `{context.storage().get_user_id_from_chat_id(chat_id)}`",
            f"Chat ID: `{context.storage().get_current_state(chat_id)}`",
            f"Playlist: `{context.storage().get_playlist_from_dynamodb(chat_id)}`",
            f"User ID from Channel Credentials: `{context.storage().get_user_id_from_channel_credentials(chat_id)}`",
        ]
    )
    await update.message.reply_text(debug)


def build_application(token, storage):
    logger.info(f"token: {token}")

    # Set the custom context for each handler
    context_types = ContextTypes(context=CustomCallbackContext)
    application = (
        Application.builder()
        .token(token)
        .context_types(context_types)
        .defaults(defaults)
        .build()
    )
    application.bot_data["storage"] = storage

    register_handlers(application)
    return application


def register_handlers(application: Application):
    handlers = [
        CommandHandler("start", start),
        CommandHandler("help", help_command),
        CommandHandler("createplaylist", create_playlist),
        CommandHandler("resetplaylist", reset_playlist),
        CommandHandler("changeplaylistname", change_playlist_name),
        CommandHandler("changeplaylistimage", change_playlist_image),
        CommandHandler("playlistlink", send_playlist_link),
        CommandHandler("unlink", unlink_credentials),
        CommandHandler("debug", debug_stuff),
        MessageHandler(
            filters.TEXT & filters.Regex(spotify_link_pattern), handle_spotify_links
        ),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_playlist_name),
        MessageHandler(filters.PHOTO, handle_playlist_image),
    ]

    for handler in handlers:
        application.add_handler(handler)
