import logging
from supabase import acreate_client, AsyncClient
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL dan SUPABASE_KEY mesti ditetapkan dalam .env"
            )
        _client = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client berjaya diinisialisasi.")
    return _client


async def close_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None
