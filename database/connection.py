import ssl

import certifi
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from config.settings import (
    SSL_VERIFY,
    SUPABASE_HOST,
    SUPABASE_PASSWORD,
    SUPABASE_USERNAME,
)

# We connect through Supabase's connection pooler (IPv4-friendly and the
# recommended route) instead of the direct database address.
db_url = URL.create(
    drivername="postgresql+pg8000",
    username=SUPABASE_USERNAME,
    password=SUPABASE_PASSWORD,
    host=SUPABASE_HOST,
    port=5432,
    database="postgres",
)

if SSL_VERIFY:
    # Full verification using the trusted certificate bundle that browsers
    # and the requests library use (more complete than the Windows store).
    ssl_context = ssl.create_default_context(cafile=certifi.where())
else:
    # Local-only fallback: encrypted connection without chain verification
    # (equivalent to Postgres "sslmode=require", the default of most Postgres
    # clients). Traffic stays encrypted; server identity is not checked.
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

engine = create_engine(
    db_url,
    connect_args={"ssl_context": ssl_context, "timeout": 10},
)


def test_db_connection():
    """Tests if we can talk to the database."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False