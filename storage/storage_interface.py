from abc import ABC, abstractmethod
from enum import Enum


class BotState(Enum):
    AWAITING_PLAYLIST_IMAGE = "awaiting_playlist_image"
    CHANGING_PLAYLIST_NAME = "changing_playlist_name"
    CREATING_PLAYLIST = "creating_playlist"
    CHANGING_PLAYLIST_IMAGE = "changing_playlist_image"
    NO_STATE = None


class Storage(ABC):
    @abstractmethod
    def save_current_state(self, chat_id, state_key):
        pass

    @abstractmethod
    def get_current_state(self, chat_id):
        pass

    @abstractmethod
    def save_playlist_to_dynamodb(self, chat_id, playlist_id):
        pass

    @abstractmethod
    def get_playlist_from_dynamodb(self, chat_id):
        pass

    @abstractmethod
    def get_user_id_from_chat_id(self, chat_id):
        pass

    @abstractmethod
    def get_user_id_from_channel_credentials(self, chat_id):
        pass
