import logging
from .storage_interface import BotState, Storage


class InMemoryStorage(Storage):
    def __init__(self):
        self.bot_table = {}
        self.credentials_table = {}

    def save_current_state(self, chat_id, state_key: BotState):
        try:
            user_id = self.get_user_id_from_chat_id(chat_id)
            if user_id is None:
                user_id = self.get_user_id_from_channel_credentials(chat_id)

            if state_key is BotState.NO_STATE:
                if str(chat_id) in self.bot_table:
                    self.bot_table[str(chat_id)].pop("current_state", None)
            else:
                if str(chat_id) not in self.bot_table:
                    self.bot_table[str(chat_id)] = {}
                self.bot_table[str(chat_id)]["current_state"] = state_key.value
                self.bot_table[str(chat_id)]["user_id"] = user_id

            logging.info(
                f"Updated state in InMemoryStorage: {self.bot_table[str(chat_id)]}"
            )
        except Exception as e:
            logging.error(f"Error saving current state to InMemoryStorage: {e}")

    def get_current_state(self, chat_id):
        try:
            item = self.bot_table.get(str(chat_id), {})
            if "current_state" in item:
                state_value = item["current_state"]
                return BotState(state_value)
            return None
        except Exception as e:
            logging.error(f"Error retrieving current state from InMemoryStorage: {e}")
            return None

    def save_playlist_to_dynamodb(self, chat_id, playlist_id):
        try:
            if str(chat_id) not in self.bot_table:
                self.bot_table[str(chat_id)] = {}
            self.bot_table[str(chat_id)]["playlist_id"] = playlist_id
            self.bot_table[str(chat_id)]["user_id"] = self.get_user_id_from_chat_id(
                chat_id
            )
        except Exception as e:
            logging.error(f"Error saving to InMemoryStorage: {e}")

    def get_playlist_from_dynamodb(self, chat_id):
        try:
            item = self.bot_table.get(str(chat_id), {})
            return item.get("playlist_id")
        except Exception as e:
            logging.error(f"Error retrieving from InMemoryStorage: {e}")
            return None

    def get_user_id_from_chat_id(self, chat_id):
        try:
            item = self.bot_table.get(str(chat_id), {})
            return item.get("user_id")
        except Exception as e:
            logging.error(
                f"Error retrieving user ID from InMemoryStorage for chat_id: {chat_id}, error: {e}"
            )
            return None

    def get_user_id_from_channel_credentials(self, chat_id):
        try:
            item = self.credentials_table.get(str(chat_id), {})
            return item.get("user_id")
        except Exception as e:
            logging.error(
                f"Error retrieving user ID from InMemoryStorage for chat_id: {chat_id}, error: {e}"
            )
            return None

    def get_cached_token(self, chat_id):
        try:
            return self.credentials_table.get(str(chat_id))
        except Exception as e:
            logging.error(f"Error retrieving cached token from InMemoryStorage: {e}")
            raise

    def save_token_to_cache(self, chat_id, user_id, token_info):
        try:
            self.credentials_table[str(chat_id)] = {
                "chat_id": str(chat_id),
                "user_id": user_id,
                **token_info,
            }
            if str(chat_id) not in self.bot_table:
                self.bot_table[str(chat_id)] = {}
            self.bot_table[str(chat_id)]["user_id"] = str(user_id)
        except Exception as e:
            logging.error(f"Error saving token to InMemoryStorage: {e}")
            raise

    def delete_item(self, table, chat_id):
        try:
            table.pop(str(chat_id), None)
        except Exception as e:
            logging.error(f"Error deleting item from InMemoryStorage: {e}")
            raise

    def check_item_exists(self, table, chat_id):
        try:
            exists = str(chat_id) in table
            logging.info(f"check_item_exists: {exists}")
            return exists
        except Exception as e:
            logging.error(f"Error checking item in InMemoryStorage: {e}")
            raise
