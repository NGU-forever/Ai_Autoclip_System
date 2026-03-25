import logging
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from src.config import settings

logger = logging.getLogger(__name__)

# Global connection pool
_db_pool = None

def init_db_pool():
    global _db_pool
    if _db_pool is None:
        try:
            logger.info("Initializing database connection pool...")
            _db_pool = ThreadedConnectionPool(
                minconn=settings.db_pool_min_conn,
                maxconn=settings.db_pool_max_conn,
                dsn=settings.database_url,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            logger.info("Database connection pool initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

def close_db_pool():
    global _db_pool
    if _db_pool:
        _db_pool.closeall()
        logger.info("Database connection pool closed.")

def get_db_pool():
    """Returns the global database connection pool."""
    if _db_pool is None:
        init_db_pool()
    return _db_pool

@contextmanager
def get_db_connection():
    """
    Context manager to yield a single database connection from the pool.
    Always auto-commits on success, rolls back on exception, and returns connection to pool.
    """
    if _db_pool is None:
        init_db_pool()
        
    conn = _db_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        _db_pool.putconn(conn)

import redis.asyncio as redis

_redis_client = None

def get_redis_client():
    """
    Returns an async Redis client.
    """
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.redis_url, 
                encoding="utf-8", 
                decode_responses=True
            )
            logger.info("Redis client initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            return None
    return _redis_client
