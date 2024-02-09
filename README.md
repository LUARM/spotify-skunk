# Spotify Skunk Bot

Spotify Skunk Bot is a Telegram bot designed to enhance your music sharing experience by allowing you to create and manage Spotify playlists directly from Telegram chats. Using this bot, you can easily add songs to a playlist, change the playlist's name and cover image, and share your playlist with others, all through simple commands and interactions within Telegram.

## Features

- **Create Playlists:** Initiate a new Spotify playlist.
- **Add Songs:** Add songs to your playlist by sharing Spotify track links.
- **Change Playlist Name:** Update the name of your existing playlist.
- **Change Playlist Image:** Set a new cover image for your playlist.
- **Share Playlist:** Get a shareable link to your Spotify playlist.
- **Support for Group Chats:** Use the bot within Telegram group chats to collaboratively create and manage playlists.

## Prerequisites

Before you start using Spotify Skunk Bot, make sure you have the following:
- A Telegram account.
- A Spotify Premium account.
- Python 3.8 or newer.
- Access to AWS Lambda and DynamoDB for deployment and data storage.

## Setup

### Spotify Developer Account

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) and log in with your Spotify account.
2. Create a new application to get your `Client ID` and `Client Secret`.
3. Set the redirect URI to your AWS Lambda function URL.

### Telegram Bot

1. Contact [@BotFather](https://t.me/botfather) on Telegram to create a new bot.
2. Follow the instructions to get your bot token.

### AWS Configuration

1. Create a new Lambda function for your bot.
2. Set up a DynamoDB table named `SpotifySkunk` with `chat_id` as the primary key.
3. Deploy the bot code to AWS Lambda.

### Environment Variables

Configure the following environment variables in your AWS Lambda function:
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
- `SPOTIFY_CLIENT_ID`: Your Spotify application's client ID.
- `SPOTIFY_CLIENT_SECRET`: Your Spotify application's client secret.
- `SPOTIFY_REDIRECT_URI`: The redirect URI set in your Spotify application.

## Deployment

Package your bot application and dependencies into a ZIP file and upload it to your AWS Lambda function. Use the provided `deploy_lambda.sh` script for easy deployment.

## Usage

After deploying the bot, start a conversation with it on Telegram or add it to a group chat. Use the following commands to interact with the bot:
- `/start`: Initialize the bot.
- `/help`: Display help information.
- `/createplaylist`: Create a new Spotify playlist.
- `/changeplaylistname`: Change the name of the current playlist.
- `/changeplaylistimage`: Change the cover image of the current playlist.
- `/playlistlink`: Get the link to the current playlist.

## Contributing

Contributions to Spotify Skunk Bot are welcome! Please feel free to submit pull requests or open issues to suggest improvements or add new features.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
