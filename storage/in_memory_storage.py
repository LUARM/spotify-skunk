from .storage_interface import Storage
import logging

class InMemoryStorage(Storage):
    def __init__(self):
        self.state = {}
        self.playlists = {}
        self.users = {}
        self.tokens = {}

    def save_current_state(self, chat_id, state_key):
        self.state[chat_id] = state_key
        logging.info(f"Saved state for chat_id {chat_id}: {state_key}")

    def get_current_state(self, chat_id):
        state = self.state.get(chat_id, None)
        logging.info(f"Retrieved state for chat_id {chat_id}: {state}")
        return state

    def save_playlist_to_dynamodb(self, chat_id, playlist_id):
        self.playlists[chat_id] = playlist_id
        logging.info(f"Saved playlist for chat_id {chat_id}: {playlist_id}")

    def get_playlist_from_dynamodb(self, chat_id):
        playlist = self.playlists.get(chat_id, None)
        logging.info(f"Retrieved playlist for chat_id {chat_id}: {playlist}")
        return playlist

    def get_user_id_from_chat_id(self, chat_id):
        user_id = self.users.get(chat_id, None)
        logging.info(f"Retrieved user_id from chat_id for chat_id {chat_id}: {user_id}")
        return user_id

    def get_user_id_from_channel_credentials(self, chat_id):
        token_info = self.tokens.get(chat_id, None)
        user_id = token_info['user_id'] if token_info else None
        logging.info(f"get_user_id_from_channel_credentials: Retrieved user_id {user_id} for chat_id: {chat_id}")
        return user_id

    def get_cached_token(self, chat_id):
        token = self.tokens.get(chat_id, None)
        logging.info(f"Retrieved token for chat_id {chat_id}: {token}")
        return token

    def save_token_to_cache(self, chat_id, user_id, token_info):
        self.tokens[chat_id] = {'user_id': user_id, **token_info}
        self.users[chat_id] = user_id  # Save user ID to users dictionary
        logging.info(f"Saved token for chat_id {chat_id}: {self.tokens[chat_id]}")
        logging.info(f"Saved user_id for chat_id {chat_id}: {user_id}")

    def delete_item(self, table, chat_id):
        if table == "credentials_table":
            if chat_id in self.tokens:
                del self.tokens[chat_id]
                logging.info(f"Deleted token for chat_id {chat_id} from credentials_table")
        elif table == "bot_table":
            if chat_id in self.state:
                del self.state[chat_id]
                logging.info(f"Deleted state for chat_id {chat_id} from bot_table")
            if chat_id in self.playlists:
                del self.playlists[chat_id]
                logging.info(f"Deleted playlist for chat_id {chat_id} from bot_table")
            if chat_id in self.users:
                del self.users[chat_id]
                logging.info(f"Deleted user for chat_id {chat_id} from bot_table")

    def check_item_exists(self, table, chat_id):
        if table == "credentials_table":
            exists = chat_id in self.tokens
            logging.info(f"Checked if token exists for chat_id {chat_id} in credentials_table: {exists}")
            return exists
        elif table == "bot_table":
            exists = chat_id in self.state or chat_id in self.playlists or chat_id in self.users
            logging.info(f"Checked if item exists for chat_id {chat_id} in bot_table: {exists}")
            return exists
        return False