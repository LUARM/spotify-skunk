import unittest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, User, Chat
from telegram.ext import CallbackContext
from bot import start, help_command


class TestStartCommand(unittest.IsolatedAsyncioTestCase):
    async def test_start_command(self):
        update = MagicMock(spec=Update)

        update.message = MagicMock(spec=Message)
        update.message.chat_id = 12345
        update.message.reply_text = AsyncMock()

        context = MagicMock(spec=CallbackContext)

        await start(update, context)

        update.message.reply_text.assert_awaited_once_with(
            "Hiya! I'm your Spotify Skunk bot 🦨. /createplaylist to add songs to your playlist!"
        )


class TestHelpCommand(unittest.IsolatedAsyncioTestCase):
    async def setUp(self):
        chat = Chat(id=12345, type="public")
        user = User(id=67890, is_bot=False, first_name="Test User")
        message = Message(message_id=1, date=1609459200, chat=chat, from_user=user)
        self.update = Update(update_id=1, message=message)

    async def test_help_command(self):
        context = CallbackContext.from_update(self.update, bot=None)
        context = CallbackContext.from_update(self.update, bot=None)
        context.bot = MagicMock()
        context.bot_data = {}
        context.user_data = {}
        context.chat_data = {}
        context.match = None

        self.update.message.reply_text = AsyncMock()

        # Invoke the help command
        await help_command(self.update, context)

        # Check the response
        expected_text = (
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
        self.update.message.reply_text.assert_awaited_once_with(expected_text)


if __name__ == "__main__":
    unittest.main()
