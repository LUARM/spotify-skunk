from telegram.ext import CallbackContext as BaseCallbackContext

from storage.dynamodb_storage import DynamoDBStorage


class CustomCallbackContext(BaseCallbackContext):
    def __init__(self, application, chat_id=None, user_id=None):
        super().__init__(application=application, chat_id=chat_id, user_id=user_id)

    def storage(self) -> DynamoDBStorage:
        return self.bot_data["storage"]

    # @classmethod
    # def from_update(cls, update, application):
    #     """Override from_update to set storage."""
    #     context = super().from_update(update, application)
    #     context.storage = application.bot_data.get("storage")
    #     return context
