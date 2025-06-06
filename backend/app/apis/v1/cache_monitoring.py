"""
緩存監控 API 端點
提供緩存統計、監控和管理功能
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb_utils import get_db
from app.core.logging_utils import log_event, LogLevel
from app.services.ai_cache_manager import ai_cache_manager, CacheType, CacheStats
from app.models.user_models import User
from app.core.security import get_current_active_user

router = APIRouter()


@router.get("/statistics")
async def get_cache_statistics(
    fastapi_request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    獲取所有緩存的統計資訊
    """
    request_id = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    
    try:
        # 獲取增強的緩存統計（包含 Google Context Caching）
        enhanced_stats = await ai_cache_manager.get_enhanced_cache_statistics(db)
        cache_stats = enhanced_stats.get("local_caching", {}).get("cache_statistics", {})
        
        # 計算總體統計
        total_requests = sum(stats.total_requests for stats in cache_stats.values())
        total_hits = sum(stats.hit_count for stats in cache_stats.values())
        overall_hit_rate = total_hits / total_requests * 100 if total_requests > 0 else 0
        total_memory_usage = sum(stats.memory_usage_mb for stats in cache_stats.values())
        
        # 計算預估成本節省
        estimated_token_savings = 0
        for cache_type, stats in cache_stats.items():
            if cache_type == "schema":
                estimated_token_savings += stats.hit_count * 500  # 每次命中節省約 500 tokens
            elif cache_type == "system_instruction":
                estimated_token_savings += stats.hit_count * 200  # 每次命中節省約 200 tokens
            elif cache_type == "query_embedding":
                estimated_token_savings += stats.hit_count * 50   # 每次命中節省約 50 tokens
            elif cache_type == "ai_response":
                estimated_token_savings += stats.hit_count * 800  # 每次命中節省約 800 tokens
            elif cache_type == "prompt_template":
                estimated_token_savings += stats.hit_count * 1800  # 每次提示詞命中節省約 1800 tokens
        
        result = {
            "cache_statistics": cache_stats,
            "summary": {
                "total_requests": total_requests,
                "total_hits": total_hits,
                "overall_hit_rate": round(overall_hit_rate, 2),
                "total_memory_usage_mb": round(total_memory_usage, 2),
                "estimated_token_savings": estimated_token_savings,
                "estimated_cost_savings_usd": round(estimated_token_savings * 0.00002, 4)  # 假設每 token $0.00002
            },
            "cache_health": {
                cache_type: {
                    "status": "healthy" if stats.hit_rate > 0.3 else "needs_optimization",
                    "recommendation": _get_cache_recommendation(cache_type, stats)
                }
                for cache_type, stats in cache_stats.items()
            },
            "enhanced_statistics": enhanced_stats  # 添加完整的增強統計信息
        }
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"緩存統計查詢 - 總體命中率: {overall_hit_rate:.1f}%",
            source="api.cache_monitoring.statistics",
            user_id=str(current_user.id),
            request_id=request_id,
            details={
                "total_requests": total_requests,
                "estimated_savings": estimated_token_savings
            }
        )
        
        return result
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取緩存統計失敗: {str(e)}",
            source="api.cache_monitoring.statistics_error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="無法獲取緩存統計資訊")


@router.post("/clear/{cache_type}")
async def clear_cache(
    cache_type: str,
    fastapi_request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    清理指定類型的緩存
    """
    request_id = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    
    try:
        # 驗證緩存類型
        if cache_type == "all":
            ai_cache_manager.clear_cache()
            message = "已清理所有緩存"
        else:
            try:
                cache_type_enum = CacheType(cache_type)
                ai_cache_manager.clear_cache(cache_type_enum)
                message = f"已清理 {cache_type} 緩存"
            except ValueError:
                raise HTTPException(status_code=400, detail=f"無效的緩存類型: {cache_type}")
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=message,
            source="api.cache_monitoring.clear_cache",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"cache_type": cache_type}
        )
        
        return {
            "success": True,
            "message": message,
            "cache_type": cache_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"清理緩存失敗: {str(e)}",
            source="api.cache_monitoring.clear_cache_error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e), "cache_type": cache_type}
        )
        raise HTTPException(status_code=500, detail="清理緩存失敗")


@router.post("/cleanup-expired")
async def cleanup_expired_caches(
    fastapi_request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    清理過期的緩存項目
    """
    request_id = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    
    try:
        await ai_cache_manager.cleanup_expired_caches(db)
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="手動清理過期緩存完成",
            source="api.cache_monitoring.cleanup_expired",
            user_id=str(current_user.id),
            request_id=request_id
        )
        
        return {
            "success": True,
            "message": "過期緩存清理完成"
        }
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"清理過期緩存失敗: {str(e)}",
            source="api.cache_monitoring.cleanup_expired_error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="清理過期緩存失敗")


@router.get("/health")
async def get_cache_health(
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    獲取緩存系統健康狀態
    """
    try:
        cache_stats = ai_cache_manager.get_cache_statistics()
        
        health_status = {
            "overall_status": "healthy",
            "cache_details": {},
            "recommendations": []
        }
        
        issues_found = 0
        
        for cache_type, stats in cache_stats.items():
            cache_health = {
                "hit_rate": stats.hit_rate,
                "memory_usage_mb": stats.memory_usage_mb,
                "total_requests": stats.total_requests,
                "status": "healthy"
            }
            
            # 健康檢查邏輯
            if stats.hit_rate < 0.3 and stats.total_requests > 10:
                cache_health["status"] = "poor_performance"
                health_status["recommendations"].append(f"{cache_type} 緩存命中率偏低 ({stats.hit_rate:.1%})，建議調整緩存策略")
                issues_found += 1
            elif stats.memory_usage_mb > 100:  # 假設 100MB 為警告閾值
                cache_health["status"] = "high_memory"
                health_status["recommendations"].append(f"{cache_type} 緩存記憶體使用量較高 ({stats.memory_usage_mb:.1f}MB)")
                issues_found += 1
            
            health_status["cache_details"][cache_type] = cache_health
        
        if issues_found > 0:
            health_status["overall_status"] = "needs_attention"
        
        return health_status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法獲取緩存健康狀態: {str(e)}")


@router.get("/prompt-cache/detailed")
async def get_prompt_cache_detailed_statistics(
    fastapi_request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    獲取詳細的提示詞緩存統計資訊
    """
    request_id = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    
    try:
        # 導入 prompt manager 來獲取詳細統計
        from app.services.prompt_manager_simplified import prompt_manager_simplified, PromptType
        
        # 獲取提示詞緩存統計
        prompt_stats = await prompt_manager_simplified.get_prompt_cache_statistics(db)
        
        # 獲取每個提示詞類型的緩存狀態
        prompt_cache_details = {}
        for prompt_type in PromptType:
            try:
                # 獲取提示詞模板
                prompt_template = await prompt_manager_simplified.get_prompt(prompt_type, db)
                if prompt_template:
                    # 格式化提示詞以獲取長度
                    system_prompt, _ = prompt_manager_simplified.format_prompt(
                        prompt_template,
                        apply_chinese_instruction=True,
                        **{var: f"[{var}_placeholder]" for var in prompt_template.variables}
                    )
                    
                    # 檢查是否有緩存
                    cache_key = f"{prompt_type.value}_system"
                    cached_info = ai_cache_manager.get_cached_prompt_info(cache_key)
                    
                    prompt_cache_details[prompt_type.value] = {
                        "description": prompt_template.description,
                        "version": prompt_template.version,
                        "estimated_tokens": len(system_prompt.split()) * 1.3,  # 粗略估算
                        "is_cached": cached_info is not None,
                        "cache_type": cached_info.get("cache_type") if cached_info else None,
                        "cache_created_at": cached_info.get("created_at").isoformat() if cached_info and cached_info.get("created_at") else None
                    }
                else:
                    prompt_cache_details[prompt_type.value] = {
                        "description": "模板未找到",
                        "is_cached": False
                    }
            except Exception as e:
                prompt_cache_details[prompt_type.value] = {
                    "error": str(e),
                    "is_cached": False
                }
        
        result = {
            "prompt_cache_statistics": prompt_stats,
            "prompt_types_detail": prompt_cache_details,
            "summary": {
                "total_prompt_types": len(PromptType),
                "cached_prompt_types": sum(1 for details in prompt_cache_details.values() if details.get("is_cached", False)),
                "google_context_cached": sum(1 for details in prompt_cache_details.values() 
                                           if details.get("cache_type") == "google_context"),
                "local_cached": sum(1 for details in prompt_cache_details.values() 
                                  if details.get("cache_type") == "local")
            }
        }
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="提示詞緩存詳細統計查詢",
            source="api.cache_monitoring.prompt_cache_detailed",
            user_id=str(current_user.id),
            request_id=request_id
        )
        
        return result
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取提示詞緩存詳細統計失敗: {str(e)}",
            source="api.cache_monitoring.prompt_cache_detailed_error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="無法獲取提示詞緩存詳細統計")


@router.post("/prompt-cache/optimize-all")
async def optimize_all_prompt_caches(
    fastapi_request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    優化所有提示詞緩存
    """
    request_id = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    
    try:
        # 導入所需的模組
        from app.services.prompt_manager_simplified import prompt_manager_simplified, PromptType
        
        optimization_results = {}
        success_count = 0
        
        for prompt_type in PromptType:
            try:
                # 獲取提示詞模板
                prompt_template = await prompt_manager_simplified.get_prompt(prompt_type, db)
                if not prompt_template:
                    optimization_results[prompt_type.value] = {
                        "status": "skipped",
                        "reason": "模板未找到"
                    }
                    continue
                
                # 格式化提示詞
                system_prompt, _ = prompt_manager_simplified.format_prompt(
                    prompt_template,
                    apply_chinese_instruction=True,
                    **{var: f"[{var}_placeholder]" for var in prompt_template.variables}
                )
                
                # 創建緩存
                cache_id = await ai_cache_manager.get_or_create_prompt_cache(
                    db=db,
                    prompt_type=f"{prompt_type.value}_system",
                    prompt_content=system_prompt,
                    prompt_version=prompt_template.version,
                    ttl_hours=24,
                    user_id=str(current_user.id)
                )
                
                if cache_id:
                    cached_info = ai_cache_manager.get_cached_prompt_info(cache_id)
                    optimization_results[prompt_type.value] = {
                        "status": "success",
                        "cache_id": cache_id,
                        "cache_type": cached_info.get("cache_type") if cached_info else "unknown",
                        "token_count": cached_info.get("token_count") if cached_info else None
                    }
                    success_count += 1
                else:
                    optimization_results[prompt_type.value] = {
                        "status": "failed",
                        "reason": "無法創建緩存"
                    }
                    
            except Exception as e:
                optimization_results[prompt_type.value] = {
                    "status": "error",
                    "error": str(e)
                }
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"提示詞緩存批量優化完成: {success_count}/{len(PromptType)} 成功",
            source="api.cache_monitoring.optimize_all_prompts",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"success_count": success_count, "total_count": len(PromptType)}
        )
        
        return {
            "success": True,
            "message": f"提示詞緩存優化完成: {success_count}/{len(PromptType)} 成功",
            "optimization_summary": {
                "total_prompts": len(PromptType),
                "successful_optimizations": success_count,
                "success_rate": f"{(success_count/len(PromptType))*100:.1f}%" if len(PromptType) > 0 else "0%"
            },
            "detailed_results": optimization_results
        }
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"提示詞緩存批量優化失敗: {str(e)}",
            source="api.cache_monitoring.optimize_all_prompts_error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="提示詞緩存優化失敗")


def _get_cache_recommendation(cache_type: str, stats: CacheStats) -> str:
    """
    根據緩存統計提供優化建議
    """
    if stats.total_requests == 0:
        return "緩存尚未使用"
    
    hit_rate = stats.hit_rate
    
    if cache_type == "prompt_template":
        if hit_rate > 0.9:
            return "提示詞緩存運行優異，大幅節省 token 成本"
        elif hit_rate > 0.7:
            return "提示詞緩存表現良好，有效節省成本"
        elif hit_rate > 0.4:
            return "提示詞緩存需要優化，建議檢查緩存策略"
        else:
            return "提示詞緩存效果不佳，建議重新配置"
    else:
        if hit_rate > 0.8:
            return "緩存運行良好"
        elif hit_rate > 0.5:
            return "緩存表現尚可，可考慮增加緩存大小或調整 TTL"
        elif hit_rate > 0.2:
            return "緩存命中率偏低，建議檢查緩存策略和配置"
        else:
            return "緩存效果不佳，建議重新評估緩存策略" 