import boto3
import logging
from .storage_interface import BotState, Storage
import os


class DynamoDBStorage(Storage):
    def __init__(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        self.bot_table = dynamodb.Table(os.getenv("BOT_TABLE"))
        self.credentials_table = dynamodb.Table(os.getenv("CREDENTIALS_TABLE"))

    def save_current_state(self, chat_id, state_key: BotState):
        try:
            user_id = self.get_user_id_from_chat_id(chat_id)
            if user_id is None:
                user_id = self.get_user_id_from_channel_credentials(chat_id)

            if state_key is BotState.NO_STATE:
                response = self.bot_table.update_item(
                    Key={"chat_id": str(chat_id)},
                    UpdateExpression="REMOVE current_state",
                    ReturnValues="UPDATED_NEW",
                )
            else:
                response = self.bot_table.update_item(
                    Key={"chat_id": str(chat_id)},
                    UpdateExpression="SET current_state = :state, user_id = :uid",
                    ExpressionAttributeValues={
                        ":state": state_key.value,
                        ":uid": user_id,
                    },
                    ReturnValues="UPDATED_NEW",
                )
            logging.info(f"Updated state in DynamoDB: {response}")
            return response
        except Exception as e:
            logging.error(f"Error saving current state to DynamoDB: {e}")

    def get_current_state(self, chat_id):
        try:
            response = self.bot_table.get_item(Key={"chat_id": str(chat_id)})
            if "Item" in response and "current_state" in response["Item"]:
                state_value = response["Item"]["current_state"]
                return BotState(state_value)
            return None
        except Exception as e:
            logging.error(f"Error retrieving current state from DynamoDB: {e}")
            return None

    def save_playlist_to_dynamodb(self, chat_id, playlist_id):
        try:
            self.bot_table.put_item(
                Item={
                    "chat_id": str(chat_id),
                    "playlist_id": playlist_id,
                    "user_id": self.get_user_id_from_chat_id(chat_id),
                }
            )
        except Exception as e:
            logging.error(f"Error saving to DynamoDB: {e}")

    def get_playlist_from_dynamodb(self, chat_id):
        try:
            response = self.bot_table.get_item(Key={"chat_id": str(chat_id)})
            if "Item" in response:
                playlist_id = response["Item"].get("playlist_id")
                return playlist_id
            return None
        except Exception as e:
            logging.error(f"Error retrieving from DynamoDB: {e}")
            return None

    def get_user_id_from_chat_id(self, chat_id):
        try:
            response = self.bot_table.get_item(Key={"chat_id": str(chat_id)})
            if "Item" in response and "user_id" in response["Item"]:
                return response["Item"]["user_id"]
            else:
                logging.info(
                    f"get_user_id_from_chat_id: No user_id found for chat_id: {chat_id}: {response}"
                )
                return None
        except Exception as e:
            logging.error(
                f"Error retrieving user ID from DynamoDB for chat_id: {chat_id}, error: {e}"
            )
            return None

    def get_user_id_from_channel_credentials(self, chat_id):
        try:
            response = self.credentials_table.get_item(Key={"chat_id": str(chat_id)})
            if "Item" in response and "user_id" in response["Item"]:
                return response["Item"]["user_id"]
            else:
                logging.info(
                    f"get_user_id_from_channel_credentials: No user_id found for chat_id: {chat_id}: {response}"
                )
                return None
        except Exception as e:
            logging.error(
                f"Error retrieving user ID from DynamoDB for chat_id: {chat_id}, error: {e}"
            )
            return None

    def get_cached_token(self, chat_id):
        try:
            response = self.credentials_table.get_item(Key={"chat_id": str(chat_id)})
            if "Item" in response:
                return response["Item"]
            return None
        except Exception as e:
            logging.error(f"Error retrieving cached token from DynamoDB: {e}")
            raise

    def save_token_to_cache(self, chat_id, user_id, token_info):
        try:
            self.credentials_table.put_item(
                Item={
                    "chat_id": str(chat_id),
                    "user_id": user_id,
                    **token_info,
                }
            )
            self.bot_table.update_item(
                Key={"chat_id": str(chat_id)},
                UpdateExpression="SET user_id = :uid",
                ExpressionAttributeValues={":uid": str(user_id)},
            )
        except Exception as e:
            logging.error(f"Error saving token to DynamoDB: {e}")
            raise

    def delete_item(self, table, chat_id):
        try:
            table.delete_item(Key={"chat_id": str(chat_id)})
        except Exception as e:
            logging.error(f"Error deleting item from DynamoDB: {e}")
            raise

    def check_item_exists(self, table, chat_id):
        try:
            response = table.get_item(Key={"chat_id": str(chat_id)})
            logging.info(f"check_item_exists: {response}")
            return "Item" in response
        except Exception as e:
            logging.error(f"Error checking item in DynamoDB: {e}")
            raise
