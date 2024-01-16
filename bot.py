import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import logging
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# Initialize logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Spotify API credentials
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI =a.wd os.getenv('SPOTIFY_REDIRECT_URI')


user_playlists = {}

# Your bot's API token
TOKEN = os.getenv('TELERGRAM_BOT_TOKEN')
application = Application.builder().token(TOKEN).build()

spotify_link_pattern = r'https://open\.spotify\.com/track/([a-zA-Z0-9]+)'

# Initialize Spotify OAuth
sp_oauth = SpotifyOAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, scope='playlist-modify-public')


# Define a command handler function
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Hello! I'm your bot. Send me Spotify links!")


# Command handler for creating a new playlist
async def create_playlist(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    await update.message.reply_text("Please enter a name for your new playlist:")
    context.user_data[user_id] = {'creating_playlist': True}
    # context.user_data[user_id]['creating_playlist'] = True

# Function to create a new Spotify playlist
def create_spotify_playlist(playlist_name):
    sp = spotipy.Spotify(auth_manager=sp_oauth)
    user_id = sp.current_user()['id']
    playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=True)
    return playlist['id']

# Function to add tracks to a Spotify playlist
def add_track_to_spotify_playlist(playlist_id, track_id):
    sp = spotipy.Spotify(auth_manager=sp_oauth)
    sp.playlist_add_items(playlist_id, [f'spotify:track:{track_id}'])

# Message handler function for playlist name input
async def handle_playlist_name(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # Check if the user is flagged as creating a playlist and doesn't have an existing playlist
    if (user_id in context.user_data and context.user_data[user_id].get('creating_playlist') 
        and user_id not in user_playlists):
        playlist_name = update.message.text.strip()

        # Use the Spotify API to create a new playlist
        playlist_id = create_spotify_playlist(playlist_name)
        user_playlists[user_id] = {'playlist_id': playlist_id}
        await update.message.reply_text(f"Created new playlist: {playlist_name}")

        # Reset the creating_playlist flag
        context.user_data[user_id]['creating_playlist'] = False
    else:
        if user_id in user_playlists:
            # Inform the user that they already have a playlist
            await update.message.reply_text("You already have a created playlist.")
        else:
            # Handle other cases, such as when the user didn't start the playlist creation process
            await update.message.reply_text("Please use /createplaylist to start creating a playlist.")

        
async def handle_spotify_links(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    message_text = update.message.text
    match = re.search(spotify_link_pattern, message_text)

    if user_id in context.user_data and context.user_data[user_id].get('creating_playlist'):
        # If the user is still flagged as creating a playlist, ignore Spotify links
        return

    if match:
        track_id = match.group(1)

        if user_id in user_playlists:
            # User has an existing playlist; add the track to it
            playlist_id = user_playlists[user_id]['playlist_id']
            
            # Use the Spotify API to add the track to the playlist
            add_track_to_spotify_playlist(playlist_id, track_id)
            await update.message.reply_text(f"Added Spotify track to your playlist!")
        else:
            await update.message.reply_text("Please create a new playlist using /createplaylist or specify an existing playlist.")
    else:
        await update.message.reply_text("I couldn't find a Spotify link in your message.")


# Create an application instance


# Add handlers to the application
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('createplaylist', create_playlist))
application.add_handler(MessageHandler(filters.TEXT & filters.Regex(spotify_link_pattern), handle_spotify_links))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_playlist_name)) 


# Start the bot
application.run_polling()

