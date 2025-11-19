import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

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

        # Conversations collection
        # user_id: 按用戶ID查詢對話
        await db.conversations.create_index("user_id")
        # 複合索引：按用戶ID和更新時間查詢（用於列出用戶對話）
        await db.conversations.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
        # created_at: 按創建時間降序查詢
        await db.conversations.create_index([("created_at", DESCENDING)])

        logger.info("資料庫索引檢查並創建完成。")
    except Exception as e:
        logger.error(f"創建資料庫索引時發生錯誤: {e}")
