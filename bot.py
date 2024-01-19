import asyncio
import base64
import os
import spotipy
import logging
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# Load environment variables and configure logging
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Spotify API credentials and initialization
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')
sp_oauth = SpotifyOAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, 
                        scope='playlist-modify-public ugc-image-upload')

# Global variables
chat_playlists = {}  
spotify_link_pattern = r'https://open\.spotify\.com/track/([a-zA-Z0-9]+)'

# -----------------------------------------------
# Spotify Utility Functions
# -----------------------------------------------

def add_track_to_spotify_playlist(playlist_id, track_id):
    try:
        sp = spotipy.Spotify(auth_manager=sp_oauth)
        sp.playlist_add_items(playlist_id, [f'spotify:track:{track_id}'])
        return True
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 403:
            logging.error("Insufficient client scope for modifying the playlist.")
        else:
            logging.error(f"An error occurred: {e}")
        return False
    

def change_spotify_playlist_name(playlist_id, new_name):
    try:
        sp = spotipy.Spotify(auth_manager=sp_oauth)
        sp.playlist_change_details(playlist_id, name=new_name)
        return True
    except Exception as e:  # Broad catch for debugging
        logging.error(f"Error in changing playlist name: {e}")
        return False

    
def create_spotify_playlist(playlist_name):
    sp = spotipy.Spotify(auth_manager=sp_oauth)
    user_id = sp.current_user()['id']
    playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=True)
    return playlist['id']

async def handle_playlist_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id

    if context.user_data.get(chat_id, {}).get('awaiting_playlist_image') or (chat_id in chat_playlists and context.user_data.get(chat_id, {}).get('changing_playlist_image')):
        photo = update.message.photo[-1]  
        await update.message.reply_text("Processing your image, please wait...")
        try:
            photo_file = await context.bot.get_file(photo.file_id)
            photo_bytes = await photo_file.download_as_bytearray()
            base64_image = base64.b64encode(photo_bytes).decode('utf-8')
            async def upload_image():
                playlist_id = chat_playlists[chat_id]['playlist_id']
                sp = spotipy.Spotify(auth_manager=sp_oauth)
                sp.playlist_upload_cover_image(playlist_id, base64_image)
            await asyncio.wait_for(upload_image(), timeout=30)
            await update.message.reply_text("Playlist cover image set successfully!")
            if chat_id in chat_playlists and 'playlist_id' in chat_playlists[chat_id]:
                playlist_id = chat_playlists[chat_id]['playlist_id']
                playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
                await update.message.reply_text(f"Here's your playlist link: {playlist_url}")
            else:
                await update.message.reply_text("Error: Currently unable to retrieve the playlist link.")
            context.user_data[chat_id]['awaiting_playlist_image'] = False
        except asyncio.TimeoutError:
            await update.message.reply_text("Image upload timed out. Please try again.")
        except Exception as e:
            await update.message.reply_text(f"An error occurred: {e}")
    else: 
        await update.message.reply_text("Looks like you are trying to set a image for a nonexistent playlist.")


async def handle_playlist_name(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.from_user.id

    if context.user_data.get(chat_id, {}).get('changing_playlist_name'):
        if chat_id in chat_playlists:
            new_name = update.message.text.strip()
            if chat_id in chat_playlists and 'playlist_id' in chat_playlists[chat_id]:
                playlist_id = chat_playlists[chat_id]['playlist_id']
            if change_spotify_playlist_name(playlist_id, new_name):
                await update.message.reply_text(f"Playlist name changed to: {new_name}")
            else:
                await update.message.reply_text("Failed to change the playlist name. Please try again later.")
            context.user_data[chat_id]['changing_playlist_name'] = False
        else:
            await update.message.reply_text("Make sure you have a playlist created before changing the name.")
    if (chat_id in context.user_data and context.user_data[chat_id].get('creating_playlist') 
        and chat_id not in chat_playlists):
        playlist_name = update.message.text.strip()
        playlist_id = create_spotify_playlist(playlist_name)
        chat_playlists[chat_id] = {'playlist_id': playlist_id}
        context.user_data[chat_id]['awaiting_playlist_image'] = True
        await update.message.reply_text(f"Created new playlist: {playlist_name}. Now please send me an cool image to set as your playlist cover 😎.")
        context.user_data[chat_id]['creating_playlist'] = False
    else:
        return
    
async def handle_spotify_links(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    message_text = update.message.text
    match = re.search(spotify_link_pattern, message_text)
    if chat_id in context.user_data and context.user_data[chat_id].get('creating_playlist'):
        # If the user is still flagged as creating a playlist, ignore Spotify links
        return
    if match and chat_id in chat_playlists:
        track_id = match.group(1)
        playlist_id = chat_playlists[chat_id]['playlist_id']
        if add_track_to_spotify_playlist(playlist_id, track_id):
                await update.message.reply_text("Added Spotify track to your playlist!")
                await update.message.reply_text("🦨 ❤️ 🎶")
        else:
            await update.message.reply_text("Failed to add the track. Make sure you have the correct permissions or that the Playlist still exist.")
    else:
        await update.message.reply_text("Please create a new playlist using /createplaylist or specify an existing playlist.")

# -----------------------------------------------
# Telegram Command Handlers
# -----------------------------------------------
    
async def change_playlist_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id in chat_playlists:
        await update.message.reply_text("Please send the new image for your playlist:")
        context.user_data[chat_id] = {'changing_playlist_image': True}
    else:
        await update.message.reply_text("No playlist found for this chat. Create one with /createplaylist.")

async def change_playlist_name(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id in chat_playlists:
        await update.message.reply_text("Please enter the new name for your playlist:")
        context.user_data[chat_id] = {'changing_playlist_name': True}
    else:
        await update.message.reply_text("No playlist found for this chat. Create one with /createplaylist.")

async def create_playlist(update: Update, context: CallbackContext) -> bool:
    chat_id = update.effective_chat.id
    if chat_id in chat_playlists:
        await update.message.reply_text("A playlist has already been created for this chat.")
        return
    context.user_data[chat_id] = context.user_data.get(chat_id, {})
    await update.message.reply_text("Please enter a name for your new playlist:")
    context.user_data[chat_id]['creating_playlist'] = True

async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "Here are the commands you can use:\n"
        "/start - Start interacting with the bot\n"
        "/createplaylist - Create a new Spotify playlist\n"
        "/changeplaylistname - Change the name of the current playlist\n"
        "/changeplaylistimage - Change the image of the current playlist\n"
        "/resetplaylist - Reset so you can create a new playlist\n"
        "/playlistlink - Get the link to the current playlist\n"
        "/help - Show this help message\n"
        "\nJust send me a Spotify track link to add it to your playlist!"
    )
    await update.message.reply_text(help_text)

async def reset_playlist(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id in chat_playlists:
        del chat_playlists[chat_id]
    context.user_data[chat_id] = {}
    await update.message.reply_text("The current playlist has been reset. You can create a new playlist with /createplaylist.")

async def send_playlist_link(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    if chat_id in chat_playlists and 'playlist_id' in chat_playlists[chat_id]:
        playlist_id = chat_playlists[chat_id]['playlist_id']
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        await update.message.reply_text(f"Here's your playlist link: {playlist_url}")
    else:
        await update.message.reply_text("No playlist found for this chat.")

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Hiya! I'm your Spotify Skunk bot 🦨. /createplaylist so I can add spotify links as tracks in your playlist! ")

def main():
    TOKEN = os.getenv('TELERGRAM_BOT_TOKEN')
    application = Application.builder().token(TOKEN).build()

    # Define and add handlers
    handlers = [
        CommandHandler('start', start),
        CommandHandler('help', help_command),
        CommandHandler('createplaylist', create_playlist),
        CommandHandler('resetplaylist', reset_playlist),
        CommandHandler('changeplaylistname', change_playlist_name),
        CommandHandler('changeplaylistimage', change_playlist_image),
        CommandHandler('playlistlink', send_playlist_link),
        MessageHandler(filters.TEXT & filters.Regex(spotify_link_pattern), handle_spotify_links),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_playlist_name),
        MessageHandler(filters.PHOTO, handle_playlist_image)
    ]

    for handler in handlers:
        application.add_handler(handler)

    application.run_polling()

if __name__ == '__main__':
    main()

