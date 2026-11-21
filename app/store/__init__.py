from app.config import Settings
from app.store.base import Store


def get_store(settings: Settings) -> Store:
    if settings.store_backend == "postgres":
        from app.store.pg_store import PgStore

        store: Store = PgStore(settings.database_url)
    else:
        from app.store.sqlite_store import SqliteStore

        store = SqliteStore(settings.sqlite_path)
    store.init_schema(settings.embed_dim)
    return store
