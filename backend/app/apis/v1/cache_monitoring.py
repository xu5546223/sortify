"""
統一緩存監控 API

提供緩存統計、內容查看和管理功能
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb_utils import get_db
from app.core.logging_utils import log_event, LogLevel
from app.services.cache import unified_cache, CacheNamespace
from app.models.user_models import User
from app.core.security import get_current_active_user

router = APIRouter()


@router.get("/statistics")
async def get_cache_statistics(
    request: Request,
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    獲取緩存統計信息
    
    返回：
    - 整體命中率
    - 各層緩存統計
    - 各命名空間統計
    """
    try:
        stats = await unified_cache.get_statistics()
        
        return {
            "success": True,
            "data": {
                "overall_hit_rate": stats.get("overall_hit_rate", 0),
                "timestamp": stats.get("timestamp"),
                "layers": stats.get("layers", {}),
                "summary": {
                    "memory_healthy": stats.get("layers", {}).get("memory", {}).get("hits", 0) > 0,
                    "redis_healthy": stats.get("layers", {}).get("redis", {}).get("hits", 0) > 0,
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取緩存統計失敗: {str(e)}")


@router.get("/health")
async def get_cache_health(
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    獲取緩存系統健康狀態
    """
    try:
        health = await unified_cache.health_check()
        
        all_healthy = all(health.values())
        
        return {
            "success": True,
            "data": {
                "overall_status": "healthy" if all_healthy else "degraded",
                "layers": health,
                "details": {
                    "memory": {
                        "status": "healthy" if health.get("memory") else "unhealthy",
                        "message": "記憶體緩存正常" if health.get("memory") else "記憶體緩存不可用"
                    },
                    "redis": {
                        "status": "healthy" if health.get("redis") else "degraded",
                        "message": "Redis 正常" if health.get("redis") else "Redis 不可用（已降級到記憶體）"
                    }
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"健康檢查失敗: {str(e)}")


@router.get("/namespaces")
async def get_cache_namespaces(
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    獲取所有緩存命名空間信息
    """
    try:
        namespaces_info = []
        
        for namespace in CacheNamespace:
            namespaces_info.append({
                "name": namespace.value,
                "display_name": _get_namespace_display_name(namespace),
                "description": _get_namespace_description(namespace),
            })
        
        return {
            "success": True,
            "data": {
                "namespaces": namespaces_info,
                "total": len(namespaces_info)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取命名空間失敗: {str(e)}")


@router.post("/clear/{namespace}")
async def clear_namespace_cache(
    namespace: str,
    pattern: Optional[str] = Query(None, description="清理模式，如 'test*'"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> Dict[str, Any]:
    """
    清理指定命名空間的緩存
    """
    try:
        # 驗證命名空間
        try:
            cache_namespace = CacheNamespace(namespace)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"無效的命名空間: {namespace}")
        
        # 清理緩存
        result = await unified_cache.clear(
            namespace=cache_namespace,
            pattern=pattern
        )
        
        # 記錄日誌
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"清理緩存命名空間: {namespace}",
            source="api.cache_monitoring.clear",
            user_id=str(current_user.id),
            details={
                "namespace": namespace,
                "pattern": pattern,
                "cleared_count": sum(result.values()) if isinstance(result, dict) else result
            }
        )
        
        return {
            "success": True,
            "message": f"已清理命名空間 {namespace}",
            "data": {
                "namespace": namespace,
                "pattern": pattern,
                "result": result
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理緩存失敗: {str(e)}")


@router.get("/content/{namespace}")
async def get_namespace_content(
    namespace: str,
    limit: int = Query(50, ge=1, le=100, description="返回的最大數量"),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    獲取指定命名空間的緩存內容（僅顯示鍵和基本信息）
    
    注意：為了安全，不直接返回緩存值，只返回鍵的列表
    """
    try:
        # 驗證命名空間
        try:
            cache_namespace = CacheNamespace(namespace)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"無效的命名空間: {namespace}")
        
        # 獲取統計信息（作為內容概覽）
        stats = await unified_cache.get_statistics()
        
        return {
            "success": True,
            "data": {
                "namespace": namespace,
                "display_name": _get_namespace_display_name(cache_namespace),
                "description": _get_namespace_description(cache_namespace),
                "statistics": stats.get("layers", {}),
                "note": "完整內容查看需要使用專用調試工具"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取緩存內容失敗: {str(e)}")


@router.get("/summary")
async def get_cache_summary(
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    獲取緩存總覽（適合在前端儀表板顯示）
    """
    try:
        stats = await unified_cache.get_statistics()
        health = await unified_cache.health_check()
        
        # 計算總體統計
        memory_stats = stats.get("layers", {}).get("memory", {})
        redis_stats = stats.get("layers", {}).get("redis", {})
        
        return {
            "success": True,
            "data": {
                "overview": {
                    "overall_hit_rate": stats.get("overall_hit_rate", 0),
                    "status": "healthy" if all(health.values()) else "degraded",
                    "active_layers": len([k for k, v in health.items() if v])
                },
                "layers": {
                    "memory": {
                        "healthy": health.get("memory", False),
                        "hits": memory_stats.get("hits", 0),
                        "misses": memory_stats.get("misses", 0),
                        "hit_rate": memory_stats.get("hit_rate", 0),
                        "size": memory_stats.get("size", 0),
                        "memory_mb": memory_stats.get("memory_mb", 0.0),
                        "memory_bytes": memory_stats.get("memory_bytes", 0)
                    },
                    "redis": {
                        "healthy": health.get("redis", False),
                        "hits": redis_stats.get("hits", 0),
                        "misses": redis_stats.get("misses", 0),
                        "hit_rate": redis_stats.get("hit_rate", 0),
                        "memory_mb": redis_stats.get("memory_mb", 0.0),
                        "memory_bytes": redis_stats.get("memory_bytes", 0)
                    }
                },
                "namespaces": [
                    {
                        "name": ns.value,
                        "display_name": _get_namespace_display_name(ns),
                    }
                    for ns in CacheNamespace
                ],
                "timestamp": stats.get("timestamp")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取緩存總覽失敗: {str(e)}")


# 輔助函數

def _get_namespace_display_name(namespace: CacheNamespace) -> str:
    """獲取命名空間的顯示名稱"""
    name_map = {
        CacheNamespace.PROMPT: "提示詞",
        CacheNamespace.CONVERSATION: "對話",
        CacheNamespace.EMBEDDING: "向量嵌入",
        CacheNamespace.AI_RESPONSE: "AI 回答",
        CacheNamespace.DOCUMENT: "文檔",
        CacheNamespace.USER_SESSION: "用戶會話",
        CacheNamespace.SCHEMA: "資料庫 Schema",
        CacheNamespace.GENERAL: "通用",
    }
    return name_map.get(namespace, namespace.value)


def _get_namespace_description(namespace: CacheNamespace) -> str:
    """獲取命名空間的描述"""
    desc_map = {
        CacheNamespace.PROMPT: "AI 提示詞模板緩存，TTL: 2小時",
        CacheNamespace.CONVERSATION: "對話上下文緩存，TTL: 1小時",
        CacheNamespace.EMBEDDING: "查詢向量嵌入緩存，TTL: 10分鐘",
        CacheNamespace.AI_RESPONSE: "AI 回答結果緩存，TTL: 15分鐘",
        CacheNamespace.DOCUMENT: "文檔內容緩存，TTL: 30分鐘",
        CacheNamespace.USER_SESSION: "用戶會話數據緩存，TTL: 1小時",
        CacheNamespace.SCHEMA: "資料庫 Schema 緩存，TTL: 6小時",
        CacheNamespace.GENERAL: "通用數據緩存，TTL: 5分鐘",
    }
    return desc_map.get(namespace, "")
