import json
import unittest
from datetime import datetime
from typing import Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

from telegram import Update, Message, User, Chat, MessageEntity
from telegram._utils.defaultvalue import DEFAULT_NONE
from telegram._utils.types import ODVInput
from telegram.ext import CallbackContext, Application, ContextTypes
from telegram.request import BaseRequest, RequestData

import bot
from bot import start, help_command, register_handlers
from custom_callback_contex import CustomCallbackContext
from storage.in_memory_storage import InMemoryStorage


def counter(initial=1):
    """counter creates a Python generator yielding incrementing integers."""
    i = initial
    while True:
        i += 1
        yield i


class UnexpectedTelegramEndpoint(Exception):
    pass


class UnexpectedTelegramApiCall(Exception):
    pass


class FakeTelegramApiServer(BaseRequest):
    """FakeTelegramApiServerRequest implements a fake Telegram API server by overriding the default networking
    implementation with one that operates entirely in-memory.
    You can extract the outbound requests by inspecting the .messages_sent list.
    """

    fake_api_endpoint = "https://localhost/"
    fake_token = "faketoken"

    def __init__(self, bot_user: User):
        """Initialize a FakeTelegramApiServer.
        :arg bot_user Describes the identity of the bot, as would be represented by the Telegram API server.
        """
        super().__init__()
        self.bot_user = bot_user
        # Collected outbound requests will be stored here.
        self.messages_sent = []

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def do_request(
        self,
        url: str,
        method: str,
        request_data: Optional[RequestData] = None,
        read_timeout: ODVInput[float] = DEFAULT_NONE,
        write_timeout: ODVInput[float] = DEFAULT_NONE,
        connect_timeout: ODVInput[float] = DEFAULT_NONE,
        pool_timeout: ODVInput[float] = DEFAULT_NONE,
    ) -> Tuple[int, bytes]:
        """Implements a fake networking request/response."""
        expected_prefix = self.fake_api_endpoint + self.fake_token + "/"
        if not url.startswith(expected_prefix):
            raise UnexpectedTelegramEndpoint(
                f"Expected prefix of {expected_prefix} but got URL {url}"
            )
        path = url[len(expected_prefix) :]

        # AFAICT the library is only sending sendMessage and getMe requests, so these are the only two backend
        # methods we fake.
        if path == "getMe":
            return 200, json.dumps(
                {"ok": True, "result": json.loads(self.bot_user.to_json())}
            ).encode("utf-8")
        elif path == "sendMessage":
            print(f"Sending message: {request_data.parameters}")
            self.messages_sent.extend([request_data.parameters])
            # Fake a response from the Telegram servers. Note: This is not the full response that it sends to a
            # message. The real response would contain the full message that was sent.
            return 200, json.dumps({"ok": True, "result": {}}).encode("utf-8")

        # If the bot tries to make a Telegram API call to a different endpoint, just raise an exception and fail the
        # test.
        raise UnexpectedTelegramApiCall(
            f"_request_wrapper(url={path}, method={method}, request_data={request_data.json_payload}"
        )


class TestBotWithoutMocks(unittest.IsolatedAsyncioTestCase):
    """TestBotWithoutMocks allows for testing the responses generated when sending commands to the bot."""

    # Utility values to generate incrementing values for the messages we generate.
    __message_id_counter = counter()
    __update_id_counter = counter(10000)

    async def asyncSetUp(self):
        super().setUp()
        # Note: it would be nice to test group chats AND 1:1 chats but for now we are just testing group chats.
        self.chat = Chat(id=-1, type="public")
        self.bot_user = User(
            id=999, is_bot=False, first_name="Test", username="testskunkbot"
        )
        self.request_collector = FakeTelegramApiServer(self.bot_user)

        # This must match the behavior in bot.build_application /except/ for the fields that are commented.
        # TODO: unify with build_application.
        self.app = (
            Application.builder()
            .base_url(
                self.request_collector.fake_api_endpoint
            )  # disables interaction with telegram servers
            .context_types(ContextTypes(context=CustomCallbackContext))
            .defaults(bot.defaults)
            .get_updates_request(
                self.request_collector
            )  # replaces network I/O with FakeTelegramApiServerRequest
            .request(
                self.request_collector
            )  # replaces network I/O with FakeTelegramApiServerRequest
            .token(self.request_collector.fake_token)
            .updater(None)  # disables the library's polling or webhook behaviors
            .build()
        )

        # Use an in-memory database rather than dynamodb
        self.storage = InMemoryStorage()
        self.app.bot_data["storage"] = self.storage

        register_handlers(self.app)

        await self.app.initialize()

    async def asyncTearDown(self):
        await self.app.shutdown()

    async def sendMessage(self, text):
        """sendMessage sends a message to the bot.
        If the text starts with /, we assume it is a "Command" and send a slightly more special type of message to
        deal with that. Otherwise, it is just a plain text message.
        Returns the last message we received from the bot, or None if no messages were generated by the bot.
        """

        # Bot commands need to be annotated with entities=.
        if text.startswith("/"):
            message = Message(
                chat=self.chat,
                date=datetime(year=2024, month=1, day=1),
                entities=[
                    MessageEntity(type="bot_command", offset=0, length=len(text))
                ],
                from_user=self.bot_user,
                message_id=next(self.__message_id_counter),
                text=text,
            )
        else:
            # Plain text commands do not need entities=.
            message = Message(
                chat=self.chat,
                date=datetime(year=2024, month=1, day=1),
                from_user=self.bot_user,
                message_id=next(self.__message_id_counter),
                text=text,
            )

        # `update` is the Update message that we would expect to receive from the Telegram API servers.
        update = Update(update_id=next(self.__update_id_counter), message=message)

        # This app.process_update will trigger the appropriate command based on the user's message. Once it is
        # complete, we can inspect the request_collector to determine which API calls were sent to the Telegram API
        # servers.
        await self.app.process_update(
            Update.de_json(data=update.to_dict(), bot=self.app.bot)
        )

        if not self.request_collector.messages_sent:
            return None
        return self.request_collector.messages_sent.pop()

    async def test_help(self):
        response = await self.sendMessage("/help")
        self.assertTrue(response["text"].startswith("Here are the commands"))

    async def test_irrelevant_message(self):
        response = await self.sendMessage("bark bark bark")
        # This message is ignored, so there is no response.
        self.assertIsNone(response)

    async def test_unlink_before_link(self):
        response = await self.sendMessage("/unlink")
        # TODO: Fix this behavior -- /unlink on an unlinked channel should not reply with something that looks like
        # an error message.
        self.assertEqual(
            "Failed to unlink your Spotify credentials: credentials not found.",
            response["text"],
        )
        # Confirm that there are no credentials for this channel.
        self.assertIsNone(
            self.storage.get_user_id_from_channel_credentials(self.chat.id)
        )
        # Confirm that there is no state for this channel.
        self.assertIsNone(self.storage.get_current_state(self.chat.id))

    async def test_playlistlink(self):
        response = await self.sendMessage("/playlistlink")
        self.assertEqual("No playlist found for this chat.", response["text"])

    async def test_link(self):
        response = await self.sendMessage("/createplaylist")
        # TODO: verify the response contains a spotify URL
        # self.assertTrue(response["text"] contains "http...")

if __name__ == "__main__":
    unittest.main()
