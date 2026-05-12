import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH


async def create_client(user_id: int) -> TelegramClient:
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    return client


async def create_client_from_session(session_string: str) -> TelegramClient:
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()
    return client


async def send_code(client: TelegramClient, phone: str) -> str:
    result = await client.send_code_request(phone)
    return result.phone_code_hash


async def sign_in(client: TelegramClient, phone: str, code: str, phone_code_hash: str):
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        return "success"
    except SessionPasswordNeededError:
        return "2fa_required"


async def get_session_string(client: TelegramClient) -> str:
    return client.session.save()


async def fetch_user_groups(session_string: str) -> list:
    client = await create_client_from_session(session_string)
    try:
        dialogs = await client.get_dialogs()
        groups = []
        for dialog in dialogs:
            entity = dialog.entity
            if hasattr(entity, "megagroup") or hasattr(entity, "gigagroup"):
                groups.append({
                    "id": entity.id,
                    "title": dialog.name,
                    "username": getattr(entity, "username", None),
                })
            elif dialog.is_group:
                groups.append({
                    "id": entity.id,
                    "title": dialog.name,
                    "username": None,
                })
        return groups
    finally:
        await client.disconnect()


async def send_message_to_group(session_string: str, group_id: int, message: str) -> bool:
    client = await create_client_from_session(session_string)
    try:
        await client.send_message(group_id, message)
        return True
    except Exception as e:
        raise e
    finally:
        await client.disconnect()
