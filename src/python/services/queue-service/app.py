import requests
import os
import time
import json

from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    ManagedIdentityCredential,
    EnvironmentCredential,
)
from azure.storage.queue import QueueServiceClient
from azure.ai.formrecognizer import FormRecognizerClient
from azure.ai.textanalytics import TextAnalyticsClient
from azure.cosmos import CosmosClient

from smart_getenv import getenv
from dotmap import DotMap
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

sleep = getenv("AZURE_STORAGE_QUEUE_RECEIVE_SLEEP", type=bool, default=1)

credential = ChainedTokenCredential(
    AzureCliCredential(), EnvironmentCredential(), ManagedIdentityCredential()
)

queue_service_client = QueueServiceClient(
    account_url=getenv("AZURE_STORAGE_QUEUE_ENDPOINT"), credential=credential
)

queue_client = queue_service_client.get_queue_client(
    queue=getenv("AZURE_STORAGE_QUEUE_NAME", default="messages")
)

fr_client = FormRecognizerClient(
    endpoint=getenv("AZURE_FORM_RECOGNIZER_ENDPOINT"), credential=credential
)

ta_client = TextAnalyticsClient(
    endpoint=getenv("AZURE_TEXT_ANALYTICS_ENDPOINT"), credential=credential
)

cosmos_client = CosmosClient(
    url=getenv("AZURE_COSMOS_ENDPOINT"), credential=getenv("AZURE_COSMOS_KEY")
)

cosmos_database_client = cosmos_client.get_database_client(
    getenv("AZURE_COSMOS_DB", default="azimageai")
)

cosmos_container_client = cosmos_database_client.get_container_client(
    getenv("AZURE_COSMOS_CONTAINER", default="images")
)

while True:

    print("Receiving messages...")
    batches = queue_client.receive_messages(
        messages_per_page=getenv("AZURE_STORAGE_QUEUE_MSG_COUNT", default="10")
    )
    for batch in batches.by_page():
        for message in batch:
            message_json = DotMap(json.loads(message.content))

            fr_poller = fr_client.begin_recognize_content_from_url(message_json.url)
            fr_result = fr_poller.result()

            text = " ".join([line.text for page in fr_result for line in page.lines])

            print(text)
            message_json.text = text

            if text:
                ta_response = ta_client.analyze_sentiment([text])
                for doc in ta_response:
                    print(doc.sentiment)
                    message_json.sentiment = doc.sentiment

                cosmos_container_client.upsert_item(message_json.toDict())

                queue_client.delete_message(message)

            print(message_json)

    time.sleep(sleep)

