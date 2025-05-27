from asyncio import Lock
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING # 匯入 ASCENDING 和 DESCENDING
from ..core.config import settings
import logging

logger = logging.getLogger(__name__)

async def create_database_indexes(db: AsyncIOMotorDatabase):
    """
    在資料庫中為指定集合創建索引。
    如果索引已存在，則不會重複創建。
    """
    logger.info("開始檢查並創建資料庫索引...")
    try:
        # Users collection
        # username: 唯一且用於登入
        await db.users.create_index("username", unique=True)
        # email: 可選但若存在則唯一，用於查詢
        await db.users.create_index("email", unique=True, sparse=True)

        # Connected Devices collection
        # device_id: 每個裝置的唯一標識
        await db.connected_devices.create_index("device_id", unique=True)
        # user_id: 查詢特定使用者擁有的裝置
        await db.connected_devices.create_index("user_id")
        # last_active_at: 查詢最近活動的裝置 (降序)
        await db.connected_devices.create_index([("last_active_at", DESCENDING)])


        # Documents collection
        # _id (UUID) is automatically indexed by MongoDB if it's the primary key (DocumentInDBBase uses alias "_id")
        # uploader_device_id: 按上傳設備查詢文件
        await db.documents.create_index("uploader_device_id")
        # status: 按文件處理狀態查詢
        await db.documents.create_index("status")
        # created_at: 按創建時間降序查詢，獲取最新文件
        await db.documents.create_index([("created_at", DESCENDING)])
        # tags: 多鍵索引，用於按標籤查詢
        await db.documents.create_index("tags")
        # filename: 按文件名查詢，可考慮文本索引以支援更複雜的文本搜索
        await db.documents.create_index("filename")
        # 可選的文本索引 (如果需要更強大的全文搜索功能)
        # await db.documents.create_index([("filename", "text"), ("extracted_text", "text")], name="document_text_search")


        # Logs collection
        # timestamp: 按時間戳降序查詢，獲取最新日誌
        await db.logs.create_index([("timestamp", DESCENDING)])
        # level: 按日誌級別過濾
        await db.logs.create_index("level")
        # user_id: 按用戶ID過濾日誌
        await db.logs.create_index("user_id")
        # source: 按日誌來源過濾
        await db.logs.create_index("source")
        # request_id: 追蹤特定請求的日誌鏈
        await db.logs.create_index("request_id")
        # 複合索引: 常見的查詢模式 (例如，查詢特定級別的最新日誌)
        await db.logs.create_index([("timestamp", DESCENDING), ("level", ASCENDING)])
        await db.logs.create_index([("timestamp", DESCENDING), ("source", ASCENDING)])


        logger.info("資料庫索引檢查並創建完成。")
    except Exception as e:
        logger.error(f"創建資料庫索引時發生錯誤: {e}")

class MongoDBConnectionManager:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None
    is_connected: bool = False # 新增狀態標誌
    _reconnect_lock = Lock() # 新增 Lock

    async def connect_to_mongo(self):
        logger.info("開始連接到 MongoDB...")
        self.is_connected = False # 重設狀態
        try:
            self.client = AsyncIOMotorClient(
                settings.MONGODB_URL,
                uuidRepresentation='standard',  # 添加這個參數以處理 UUID 類型
                serverSelectionTimeoutMS=5000 # 添加超時以避免長時間阻塞
            )
            # 嘗試 ping server 來驗證連線
            await self.client.admin.command('ping')
            self.db = self.client[settings.DB_NAME]
            logger.info(f"成功連接到 MongoDB 資料庫: {settings.DB_NAME}")
            # 成功連接後，創建/確保索引存在
            await create_database_indexes(self.db)
            self.is_connected = True
        except Exception as e:
            logger.error(f"連接 MongoDB 或創建索引失敗: {e}")
            # 如果連接或索引創建失敗，重置 client 和 db 狀態
            if self.client: # 確保 client 不是 None 才調用 close
                self.client.close()
            self.client = None
            self.db = None
            self.is_connected = False # 明確設定為 False


    async def close_mongo_connection(self):
        if self.client:
            logger.info("關閉 MongoDB 連接...")
            self.client.close()
            logger.info("MongoDB 連接已關閉")
        self.is_connected = False # 關閉後也更新狀態

    def get_database(self) -> AsyncIOMotorDatabase | None:
        # 這個方法可以直接返回 self.db，依賴 is_connected 狀態來判斷是否可用
        if self.is_connected and self.db is not None:
            return self.db
        return None

    def get_db_client(self) -> AsyncIOMotorClient | None:
        """獲取 MongoDB 客戶端連接。"""
        if self.is_connected and self.client:
            return self.client
        return None

db_manager = MongoDBConnectionManager()

# 自定義異常，用於表示資料庫不可用
class DatabaseUnavailableError(Exception):
    pass

async def get_db() -> AsyncIOMotorDatabase:
    if not db_manager.is_connected or db_manager.db is None:
        # 使用 async with 語法來確保鎖總是被正確釋放，即使在發生異常時
        async with db_manager._reconnect_lock:
            # Double check the condition inside the lock to prevent race conditions
            if not db_manager.is_connected or db_manager.db is None:
                logger.warning("get_db() 發現資料庫未連接或 db 物件為 None，嘗試重新連接...")
                await db_manager.connect_to_mongo()
                if not db_manager.is_connected or db_manager.db is None:
                    raise DatabaseUnavailableError("資料庫連接不可用。請檢查系統設定或服務狀態。")
    return db_manager.db 