#!/usr/bin/env python
"""
批量重新分析文檔腳本

此腳本用於批量觸發文檔的重新分析，使用新的 AI 邏輯分塊策略。

使用方法:
    cd backend
    uv run python scripts/batch_reanalyze.py [選項]

選項:
    --status       只處理特定狀態的文檔 (預設: analysis_completed,completed)
    --user-id      只處理特定用戶的文檔
    --limit        限制處理的文檔數量
    --concurrency  並發數量 (預設: 1)
    --dry-run      只顯示將處理的文檔，不實際執行
    --delay        每個文檔處理後的延遲秒數 (預設: 2)
    --reset-only   只重置狀態為 pending_analysis，不執行分析（可在前端確認後手動觸發）
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime
from typing import List, Optional
import uuid

# 設置控制台編碼
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

# 添加項目根目錄到路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.config import settings
from app.db.mongodb_utils import db_manager
from app.models.document_models import DocumentStatus
from app.services.document.document_tasks_service import DocumentTasksService

# 創建服務實例
document_tasks_service = DocumentTasksService()


class BatchReanalyzer:
    def __init__(
        self,
        status_filter: List[str],
        user_id: Optional[str] = None,
        limit: Optional[int] = None,
        concurrency: int = 1,
        dry_run: bool = False,
        delay: float = 2.0,
        reset_only: bool = False
    ):
        self.status_filter = status_filter
        self.user_id = user_id
        self.limit = limit
        self.concurrency = concurrency
        self.dry_run = dry_run
        self.delay = delay
        self.reset_only = reset_only

        # 統計 (使用 lock 保護並發更新)
        self.total_docs = 0
        self.processed = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self._stats_lock = asyncio.Lock()

    async def get_documents_to_process(self, db: AsyncIOMotorDatabase) -> List[dict]:
        """獲取需要重新分析的文檔列表"""
        query = {}

        # 狀態過濾
        if self.status_filter:
            query["status"] = {"$in": self.status_filter}

        # 用戶過濾
        if self.user_id:
            try:
                query["owner_id"] = uuid.UUID(self.user_id)
            except ValueError:
                print(f"[ERROR] 無效的用戶 ID: {self.user_id}")
                return []

        # 執行查詢
        cursor = db.documents.find(
            query,
            {"_id": 1, "filename": 1, "status": 1, "owner_id": 1, "file_type": 1, "created_at": 1}
        ).sort("created_at", -1)

        if self.limit:
            cursor = cursor.limit(self.limit)

        documents = await cursor.to_list(length=None)
        return documents

    async def process_single_document(
        self,
        db: AsyncIOMotorDatabase,
        doc: dict,
        index: int,
        semaphore: asyncio.Semaphore = None
    ) -> bool:
        """處理單個文檔"""
        doc_id = str(doc["_id"])
        filename = doc.get("filename", "未知")
        owner_id = str(doc.get("owner_id", ""))

        # 使用信號量控制並發
        if semaphore:
            async with semaphore:
                return await self._do_process_document(db, doc, doc_id, filename, owner_id, index)
        else:
            return await self._do_process_document(db, doc, doc_id, filename, owner_id, index)

    async def _do_process_document(
        self,
        db: AsyncIOMotorDatabase,
        doc: dict,
        doc_id: str,
        filename: str,
        owner_id: str,
        index: int
    ) -> bool:
        """實際執行文檔處理"""
        start_time = datetime.now()
        print(f"\n[{index}/{self.total_docs}] 開始處理: {filename}")
        print(f"    ID: {doc_id} | 類型: {doc.get('file_type', '未知')}")

        if self.dry_run:
            print(f"    [DRY RUN] 跳過實際處理")
            async with self._stats_lock:
                self.processed += 1
                self.success += 1
            return True

        try:
            if self.reset_only:
                # 只重置狀態為 PENDING_ANALYSIS，不執行分析
                await db.documents.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"status": DocumentStatus.PENDING_ANALYSIS.value}}
                )
                print(f"    [OK] {filename} 狀態已重置為 pending_analysis")
            else:
                # 更新狀態為 ANALYZING
                await db.documents.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"status": DocumentStatus.ANALYZING.value}}
                )

                # 調用分析服務
                await document_tasks_service.process_document_content_analysis(
                    doc_id_str=doc_id,
                    db=db,
                    user_id_for_log=owner_id,
                    request_id_for_log=f"batch-reanalyze-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    settings_obj=settings,
                    ai_ensure_chinese_output=True
                )

                duration = (datetime.now() - start_time).total_seconds()
                print(f"    [OK] {filename} 完成 ({duration:.1f}s)")

            async with self._stats_lock:
                self.processed += 1
                self.success += 1
            return True

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            print(f"    [FAILED] {filename} 失敗 ({duration:.1f}s): {str(e)}")
            # 更新狀態為失敗
            try:
                await db.documents.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "status": DocumentStatus.ANALYSIS_FAILED.value,
                            "analysis.error_details": f"批量重新分析失敗: {str(e)}"
                        }
                    }
                )
            except Exception:
                pass

            async with self._stats_lock:
                self.processed += 1
                self.failed += 1
            return False

    async def run(self):
        """執行批量重新分析"""
        print("=" * 60)
        print("批量重新分析文檔")
        print("=" * 60)
        print(f"狀態過濾: {', '.join(self.status_filter) if self.status_filter else '全部'}")
        print(f"用戶過濾: {self.user_id or '全部用戶'}")
        print(f"數量限制: {self.limit or '無限制'}")
        print(f"並發數量: {self.concurrency}")
        print(f"處理延遲: {self.delay}秒")
        if self.reset_only:
            print(f"模式: 只重置狀態 (不執行分析)")
        else:
            print(f"模式: {'DRY RUN (不實際執行)' if self.dry_run else '正式執行'}")
        print("=" * 60)

        # 連接數據庫
        print("\n[*] 連接數據庫...")
        await db_manager.connect_to_mongo()

        if not db_manager.is_connected:
            print("[ERROR] 無法連接到數據庫")
            return

        db = db_manager.get_database()
        if db is None:
            print("[ERROR] 無法獲取數據庫實例")
            return

        print("[OK] 數據庫連接成功")

        # 初始化向量數據庫（僅在非 reset_only 模式下需要）
        if not self.reset_only:
            print("\n[*] 初始化向量數據庫...")
            try:
                from app.services.vector.vector_db_service import vector_db_service
                from app.services.vector.embedding_service import embedding_service

                # 確保 embedding 服務已初始化
                vector_dim = len(embedding_service.encode_text("test"))
                vector_db_service.create_collection(vector_dim)
                print(f"[OK] 向量數據庫已初始化 (維度: {vector_dim})")
            except Exception as e:
                print(f"[WARN] 向量數據庫初始化警告: {e}")

        # 獲取文檔列表
        print("\n[*] 獲取文檔列表...")
        documents = await self.get_documents_to_process(db)
        self.total_docs = len(documents)

        if self.total_docs == 0:
            print("[WARN] 沒有找到符合條件的文檔")
            await db_manager.close_mongo_connection()
            return

        print(f"[OK] 找到 {self.total_docs} 個文檔需要處理")

        # 確認執行
        if not self.dry_run:
            print("\n" + "!" * 60)
            if self.reset_only:
                print("警告：這將把所有選中文檔的狀態重置為 pending_analysis！")
                print("文檔不會被分析，您可以在前端確認後手動觸發分析。")
            else:
                print("警告：這將重新分析所有選中的文檔！")
            print("!" * 60)
            confirm = input("\n確定要繼續嗎？(輸入 'yes' 確認): ")
            if confirm.lower() != 'yes':
                print("[CANCELLED] 操作已取消")
                await db_manager.close_mongo_connection()
                return

        # 開始處理
        print("\n" + "=" * 60)
        print(f"開始處理... (並發數: {self.concurrency})")
        print("=" * 60)

        start_time = datetime.now()

        if self.concurrency > 1:
            # 並發處理模式
            semaphore = asyncio.Semaphore(self.concurrency)
            tasks = [
                self.process_single_document(db, doc, i, semaphore)
                for i, doc in enumerate(documents, 1)
            ]
            await asyncio.gather(*tasks)
        else:
            # 順序處理模式
            for i, doc in enumerate(documents, 1):
                await self.process_single_document(db, doc, i)

                # 延遲（避免過載）
                if i < self.total_docs and self.delay > 0 and not self.dry_run:
                    await asyncio.sleep(self.delay)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # 輸出統計
        print("\n" + "=" * 60)
        print("處理完成統計")
        print("=" * 60)
        print(f"總文檔數: {self.total_docs}")
        print(f"已處理: {self.processed}")
        print(f"成功: {self.success}")
        print(f"失敗: {self.failed}")
        print(f"跳過: {self.skipped}")
        print(f"總耗時: {duration:.2f} 秒")
        if self.processed > 0:
            print(f"平均每個: {duration / self.processed:.2f} 秒")
        print("=" * 60)

        # 關閉連接
        await db_manager.close_mongo_connection()
        print("\n[OK] 數據庫連接已關閉")


def main():
    parser = argparse.ArgumentParser(
        description="批量重新分析文檔",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 查看將處理的文檔（不實際執行）
  uv run python scripts/batch_reanalyze.py --dry-run

  # 只重置狀態為 pending_analysis（不執行分析，可在前端確認後手動觸發）
  uv run python scripts/batch_reanalyze.py --reset-only

  # 使用預設並發 (5 個同時處理)
  uv run python scripts/batch_reanalyze.py

  # 高並發快速處理 (10 個同時處理)
  uv run python scripts/batch_reanalyze.py --concurrency 10

  # 只處理前 10 個文檔
  uv run python scripts/batch_reanalyze.py --limit 10

  # 只處理特定用戶的文檔
  uv run python scripts/batch_reanalyze.py --user-id "xxxx-xxxx-xxxx"

  # 處理所有狀態的文檔
  uv run python scripts/batch_reanalyze.py --status all
        """
    )

    parser.add_argument(
        "--status",
        type=str,
        default="analysis_completed,completed",
        help="要處理的文檔狀態，用逗號分隔。使用 'all' 處理所有狀態 (預設: analysis_completed,completed)"
    )

    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="只處理特定用戶的文檔 (UUID)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制處理的文檔數量"
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="並發數量 (預設: 5，同時處理多個文檔)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只顯示將處理的文檔，不實際執行"
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="每個文檔處理後的延遲秒數 (預設: 2.0)"
    )

    parser.add_argument(
        "--reset-only",
        action="store_true",
        help="只重置狀態為 pending_analysis，不執行分析（可在前端確認後手動觸發）"
    )

    args = parser.parse_args()

    # 解析狀態過濾
    if args.status.lower() == "all":
        status_filter = []
    else:
        status_filter = [s.strip() for s in args.status.split(",")]

    # 創建重新分析器
    reanalyzer = BatchReanalyzer(
        status_filter=status_filter,
        user_id=args.user_id,
        limit=args.limit,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
        delay=args.delay,
        reset_only=args.reset_only
    )

    # 執行
    asyncio.run(reanalyzer.run())


if __name__ == "__main__":
    main()
