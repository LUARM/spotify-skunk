from .storage_interface import Storage


class InMemoryStorage(Storage):
    def __init__(self):
        self.state = {}
        self.playlists = {}
        self.users = {}

    def save_current_state(self, chat_id, state_key):
        self.state[chat_id] = state_key

    def get_current_state(self, chat_id):
        return self.state.get(chat_id, None)

    def save_playlist_to_dynamodb(self, chat_id, playlist_id):
        self.playlists[chat_id] = playlist_id

    def get_playlist_from_dynamodb(self, chat_id):
        return self.playlists.get(chat_id, None)

    def get_user_id_from_chat_id(self, chat_id):
        return self.users.get(chat_id, None)

    def get_user_id_from_channel_credentials(self, chat_id):
        return self.users.get(chat_id, None)
