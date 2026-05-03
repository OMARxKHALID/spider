import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

SCHEMA = Secret.Schema.new(
    "org.domain.Spider",
    Secret.SchemaFlags.NONE,
    {"engine-id": Secret.SchemaAttributeType.STRING}
)

def store_api_key(engine_id: str, api_key: str) -> bool:
    return Secret.password_store_sync(
        SCHEMA,
        {"engine-id": engine_id},
        Secret.COLLECTION_DEFAULT,
        f"Spider OCR API key for {engine_id}",
        api_key,
        None
    )

def load_api_key(engine_id: str) -> str | None:
    return Secret.password_lookup_sync(
        SCHEMA,
        {"engine-id": engine_id},
        None
    )

def delete_api_key(engine_id: str) -> bool:
    return Secret.password_clear_sync(
        SCHEMA,
        {"engine-id": engine_id},
        None
    )
