from asyncio import Lock
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from ..core.config import settings
import logging

logger = logging.getLogger(__name__)

class MongoDBConnectionManager:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None
    is_connected: bool = False
    _reconnect_lock = Lock()

    async def connect_to_mongo(self):
        logger.info("開始連接到 MongoDB...")
        self.is_connected = False
        try:
            self.client = AsyncIOMotorClient(
                settings.MONGODB_URL,
                uuidRepresentation='standard',
                serverSelectionTimeoutMS=5000
            )
            # 嘗試 ping server 來驗證連線
            await self.client.admin.command('ping')
            self.db = self.client[settings.DB_NAME]
            logger.info(f"成功連接到 MongoDB 資料庫: {settings.DB_NAME}")
            self.is_connected = True
        except Exception as e:
            logger.error(f"連接 MongoDB 失敗: {e}")
            if self.client:
                self.client.close()
            self.client = None
            self.db = None
            self.is_connected = False

    async def close_mongo_connection(self):
        if self.client:
            logger.info("關閉 MongoDB 連接...")
            self.client.close()
            logger.info("MongoDB 連接已關閉")
        self.is_connected = False

    def get_database(self) -> AsyncIOMotorDatabase | None:
        if self.is_connected and self.db is not None:
            return self.db
        return None

    def get_db_client(self) -> AsyncIOMotorClient | None:
        if self.is_connected and self.client:
            return self.client
        return None

db_manager = MongoDBConnectionManager()

class DatabaseUnavailableError(Exception):
    pass

async def get_db() -> AsyncIOMotorDatabase:
    if not db_manager.is_connected or db_manager.db is None:
        await db_manager._reconnect_lock.acquire()
        try:
            if not db_manager.is_connected or db_manager.db is None:
                logger.warning("get_db() 發現資料庫未連接或 db 物件為 None，嘗試重新連接...")
                await db_manager.connect_to_mongo()
                if not db_manager.is_connected or db_manager.db is None:
                    raise DatabaseUnavailableError("資料庫連接不可用。請檢查系統設定或服務狀態。")
        finally:
            db_manager._reconnect_lock.release()
    return db_manager.db