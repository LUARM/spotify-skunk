import asyncio
import base64
import boto3
import os
import spotipy
import logging
import re
import traceback
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from spotipy.oauth2 import SpotifyOAuth


# Load environment variables and configure logging
if logging.getLogger().hasHandlers():
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


def lambda_handler(event, context):
     logger.info(f"Event body type: {type(event['body'])}")
     logger.info(f"Event body content: {event['body']}")
     return asyncio.get_event_loop().run_until_complete(main(event, context))


dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('SpotifySkunk')  

def save_playlist_to_dynamodb(chat_id, playlist_id):
    try:
        table.put_item(Item={'chat_id': str(chat_id), 'playlist_id': playlist_id})
    except Exception as e:
        logging.error(f"Error saving to DynamoDB: {e}")


def get_playlist_from_dynamodb(chat_id):
    try:
        response = table.get_item(Key={'chat_id': str(chat_id)})
        if 'Item' in response:
            playlist_id = response['Item'].get('playlist_id')
            return playlist_id
        return None
    except Exception as e:
        logging.error(f"Error retrieving from DynamoDB: {e}")
        return None

# Spotify API credentials and initialization
TOKEN = os.getenv('TELERGRAM_BOT_TOKEN')
application = Application.builder().token(TOKEN).build()   

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')
sp_oauth = SpotifyOAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, 
                        scope='playlist-modify-public ugc-image-upload')
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

    if context.user_data.get(chat_id, {}).get('awaiting_playlist_image') or (context.user_data.get(chat_id, {}).get('changing_playlist_image')):
        photo = update.message.photo[-1]  
        await update.message.reply_text("Processing your image, please wait...")
        playlist_id = get_playlist_from_dynamodb(chat_id)
        if not playlist_id:
            await update.message.reply_text("No playlist found for this chat.")
            return
        try:
            photo_file = await context.bot.get_file(photo.file_id)
            photo_bytes = await photo_file.download_as_bytearray()
            base64_image = base64.b64encode(photo_bytes).decode('utf-8')
            async def upload_image():
                sp = spotipy.Spotify(auth_manager=sp_oauth)
                sp.playlist_upload_cover_image(playlist_id, base64_image)
            await asyncio.wait_for(upload_image(), timeout=30)
            await update.message.reply_text("Playlist cover image set successfully!")
       
            playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
            await update.message.reply_text(f"Here's your playlist link: {playlist_url}")
          
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
        playlist_id = get_playlist_from_dynamodb(chat_id)
        if playlist_id:
            new_name = update.message.text.strip()
            if change_spotify_playlist_name(playlist_id, new_name):
                await update.message.reply_text(f"Playlist name changed to: {new_name}")
            else:
                await update.message.reply_text("Failed to change the playlist name. Please try again later.")
            context.user_data[chat_id]['changing_playlist_name'] = False
        else:
            await update.message.reply_text("Make sure you have a playlist created before changing the name.")
    elif context.user_data.get(chat_id, {}).get('creating_playlist'):
        playlist_name = update.message.text.strip()
        playlist_id = create_spotify_playlist(playlist_name)
        save_playlist_to_dynamodb(chat_id, playlist_id)
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
        return
    playlist_id = get_playlist_from_dynamodb(chat_id)  
    if match and playlist_id:
        track_id = match.group(1)
        if add_track_to_spotify_playlist(playlist_id, track_id):
                await update.message.reply_text("Added Spotify track to your playlist!")
                await update.message.reply_text("🦨 ❤️ 🎶")
        else:
            await update.message.reply_text("Failed to add the track. Make sure you have the correct permissions or that the Playlist still exist.")
    else:
        await update.message.reply_text("Please create a new playlist using /createplaylist ")

# -----------------------------------------------
# Telegram Command Handlers
# -----------------------------------------------
    
async def change_playlist_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        await update.message.reply_text("Please send the new image for your playlist:")
        context.user_data[chat_id] = {'changing_playlist_image': True}
    else:
        await update.message.reply_text("No playlist found for this chat. Create one with /createplaylist.")

async def change_playlist_name(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        await update.message.reply_text("Please enter the new name for your playlist:")
        context.user_data[chat_id] = {'changing_playlist_name': True}
    else:
        await update.message.reply_text("No playlist found for this chat. Create one with /createplaylist.")

async def create_playlist(update: Update, context: CallbackContext) -> bool:
    chat_id = update.effective_chat.id
    playlist_id = get_playlist_from_dynamodb(chat_id)
    if playlist_id:
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
    # Delete the playlist entry from DynamoDB
    try:
        table.delete_item(Key={'chat_id': str(chat_id)})
    except Exception as e:
        logging.error(f"Error deleting from DynamoDB: {e}")
        await update.message.reply_text("Failed to reset the playlist in the database.")
        return
    # Clear any related flags in context.user_data
    context.user_data[chat_id] = {}
    await update.message.reply_text("The current playlist has been reset. You can create a new playlist with /createplaylist.")


async def send_playlist_link(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    playlist_id = get_playlist_from_dynamodb(chat_id)
    if playlist_id:
        playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
        await update.message.reply_text(f"Here's your playlist link: {playlist_url}")
    else:
        await update.message.reply_text("No playlist found for this chat.")


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Hiya! I'm your Spotify Skunk bot 🦨. /createplaylist so I can add spotify links as tracks in your playlist! ")

async def main(event, context):


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

    
    # Convert the incoming event to a Telegram Update object
    if isinstance(event['body'], str):
        body = json.loads(event['body'])
    else:
        body = event['body']

         
    try:    
        await application.initialize()
        await application.process_update(Update.de_json(body, application.bot))
    
        return {
            'statusCode': 200,
            'body': json.dumps('Success')
        }

    except Exception as exc:
        logger.exception('Error processing update')
        return {
            'statusCode': 500,
            'body': f'Error processing update: {traceback.format_exc()}'
        }


if __name__ == '__main__':
    main()

