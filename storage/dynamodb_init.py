import os
import boto3
import logging

# Initialize logging
if logging.getLogger().hasHandlers():
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# Initialize the DynamoDB resource and tables
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

bot_table_name = os.getenv("BOT_TABLE")
credentials_table_name = os.getenv("CREDENTIALS_TABLE")

logger.info(
    f"Initializing DynamoDB tables: BOT_TABLE={bot_table_name}, CREDENTIALS_TABLE={credentials_table_name}"
)

bot_table = dynamodb.Table(bot_table_name)
credentials_table = dynamodb.Table(credentials_table_name)


__all__ = ["bot_table", "credentials_table"]
