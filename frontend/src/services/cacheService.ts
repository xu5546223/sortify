import { apiClient } from './apiClient';

// 統一緩存 - 層級統計
export interface LayerStats {
  hits: number;
  misses: number;
  hit_rate: number;
  size?: number;
  memory_mb?: number;
  memory_bytes?: number;
  healthy?: boolean;
}

// 統一緩存 - 命名空間
export interface CacheNamespace {
  name: string;
  display_name: string;
  description?: string;
}

// 統一緩存 - 總覽
export interface CacheSummary {
  overview: {
    overall_hit_rate: number;
    status: 'healthy' | 'degraded';
    active_layers: number;
  };
  layers: {
    memory: LayerStats & { size: number };
    redis: LayerStats;
  };
  namespaces: Array<{
    name: string;
    display_name: string;
  }>;
  timestamp?: string;
}

// 統一緩存 - 詳細統計（用於兼容舊接口）
export interface CacheStats {
  hits: number;
  misses: number;
  hit_rate: number;
  memory_usage_mb?: number;
  size?: number;
  hit_count: number;  // 兼容
  miss_count: number;  // 兼容
  total_requests: number;  // 兼容
}

// 統一緩存 - 統計總結（用於兼容舊接口）
export interface CacheStatistics {
  cache_statistics: Record<string, CacheStats>;
  summary: {
    total_requests: number;
    total_hits: number;
    overall_hit_rate: number;
    total_memory_usage_mb: number;
    estimated_token_savings: number;
    estimated_cost_savings_usd: number;
  };
  cache_health: Record<string, {
    status: string;
    recommendation: string;
  }>;
}

// 基本回應介面
export interface CacheResponse {
  success: boolean;
  message: string;
  cache_type?: string;
}

// 緩存健康狀態介面
export interface CacheHealth {
  status: string;
  total_cache_types: number;
  healthy_caches: number;
  optimization_needed: number;
  memory_usage_status: string;
  recommendations: string[];
}

// 提示詞緩存詳細統計介面
export interface PromptCacheDetailedStats {
  prompt_cache_statistics: {
    prompt_cache_statistics: any;
    estimated_token_savings: {
      total_prompt_tokens_per_request: number;
      estimated_daily_requests: number;
      potential_daily_savings_tokens: number;
      potential_monthly_cost_savings_usd: number;
    };
    prompt_types_breakdown: Record<string, number>;
  };
  prompt_types_detail: Record<string, {
    description: string;
    version?: string;
    estimated_tokens?: number;
    is_cached: boolean;
    cache_type?: string;
    cache_created_at?: string;
    error?: string;
  }>;
  summary: {
    total_prompt_types: number;
    cached_prompt_types: number;
    google_context_cached: number;
    local_cached: number;
  };
}

// 提示詞緩存優化結果介面
export interface PromptCacheOptimizationResult {
  success: boolean;
  message: string;
  optimization_summary: {
    total_prompts: number;
    successful_optimizations: number;
    success_rate: string;
  };
  detailed_results: Record<string, {
    status: string;
    cache_id?: string;
    cache_type?: string;
    token_count?: number;
    reason?: string;
    error?: string;
  }>;
}

/**
 * 獲取緩存總覽（新的統一緩存 API）
 */
export const getCacheSummary = async (): Promise<CacheSummary> => {
  console.log('API: 獲取緩存總覽...');
  try {
    const response = await apiClient.get('/cache/summary');
    console.log('API: 緩存總覽獲取成功:', response.data);
    return response.data.data;
  } catch (error) {
    console.error('API: 獲取緩存總覽失敗:', error);
    throw error;
  }
};

/**
 * 獲取緩存統計資訊（轉換新API為舊格式以保持兼容）
 */
export const getCacheStatistics = async (): Promise<CacheStatistics> => {
  console.log('API: 獲取緩存統計資訊...');
  try {
    const summary = await getCacheSummary();
    
    // 轉換新格式到舊格式
    const memoryStats = summary.layers.memory;
    const redisStats = summary.layers.redis;
    
    const cache_statistics: Record<string, CacheStats> = {};
    
    // 為每個命名空間創建統計（簡化版）
    summary.namespaces.forEach(ns => {
      cache_statistics[ns.name] = {
        hits: memoryStats.hits,
        misses: memoryStats.misses,
        hit_rate: memoryStats.hit_rate / 100,
        memory_usage_mb: memoryStats.memory_mb || 0,  // 使用後端提供的實際內存
        size: memoryStats.size,
        hit_count: memoryStats.hits,
        miss_count: memoryStats.misses,
        total_requests: memoryStats.hits + memoryStats.misses,
      };
    });
    
    // 計算總內存（Memory + Redis）
    const totalMemoryMb = (memoryStats.memory_mb || 0) + (redisStats.memory_mb || 0);
    
    return {
      cache_statistics,
      summary: {
        total_requests: memoryStats.hits + memoryStats.misses + redisStats.hits + redisStats.misses,
        total_hits: memoryStats.hits + redisStats.hits,
        overall_hit_rate: summary.overview.overall_hit_rate,
        total_memory_usage_mb: totalMemoryMb,
        estimated_token_savings: 0,  // 新 API 沒有這個數據
        estimated_cost_savings_usd: 0,  // 新 API 沒有這個數據
      },
      cache_health: {}
    };
  } catch (error) {
    console.error('API: 獲取緩存統計資訊失敗:', error);
    throw error;
  }
};

/**
 * 獲取所有命名空間
 */
export const getCacheNamespaces = async (): Promise<CacheNamespace[]> => {
  console.log('API: 獲取緩存命名空間...');
  try {
    const response = await apiClient.get('/cache/namespaces');
    console.log('API: 命名空間獲取成功:', response.data);
    return response.data.data.namespaces;
  } catch (error) {
    console.error('API: 獲取命名空間失敗:', error);
    throw error;
  }
};

/**
 * 清理指定命名空間的緩存（新API）
 * @param namespace 命名空間名稱 ('prompt', 'conv', 'embed', 等)
 * @param pattern 可選的清理模式
 */
export const clearNamespaceCache = async (namespace: string, pattern?: string): Promise<CacheResponse> => {
  console.log(`API: 清理緩存命名空間: ${namespace}...`);
  try {
    const params = pattern ? { pattern } : {};
    const response = await apiClient.post(`/cache/clear/${namespace}`, null, { params });
    console.log('API: 緩存清理成功:', response.data);
    return {
      success: response.data.success,
      message: response.data.message,
      cache_type: namespace
    };
  } catch (error) {
    console.error(`API: 清理緩存 ${namespace} 失敗:`, error);
    throw error;
  }
};

/**
 * 清理指定類型的緩存（兼容舊API）
 */
export const clearCache = async (cacheType: string): Promise<CacheResponse> => {
  // 映射舊的緩存類型到新的命名空間
  const typeMap: Record<string, string> = {
    'schema': 'schema',
    'system_instruction': 'prompt',
    'query_embedding': 'embed',
    'document_content': 'document',
    'ai_response': 'ai_resp',
    'prompt_template': 'prompt',
    'all': 'general'  // 清理 general 命名空間
  };
  
  const namespace = typeMap[cacheType] || cacheType;
  return clearNamespaceCache(namespace);
};

/**
 * 清理過期的緩存項目（保留但使用新方式）
 */
export const cleanupExpiredCaches = async (): Promise<CacheResponse> => {
  console.log('API: 清理過期緩存（清理所有命名空間）...');
  try {
    // 新的統一緩存會自動處理過期，這裡清理 general 命名空間
    await clearNamespaceCache('general');
    return {
      success: true,
      message: '已清理緩存'
    };
  } catch (error) {
    console.error('API: 清理過期緩存失敗:', error);
    throw error;
  }
};

/**
 * 獲取緩存健康狀態（新API）
 */
export const getCacheHealth = async (): Promise<CacheHealth> => {
  console.log('API: 獲取緩存健康狀態...');
  try {
    const response = await apiClient.get('/cache/health');
    console.log('API: 緩存健康狀態獲取成功:', response.data);
    
    // 轉換新格式到舊格式
    const data = response.data.data;
    return {
      status: data.overall_status,
      total_cache_types: 2,  // memory + redis
      healthy_caches: data.layers.memory ? 1 : 0,
      optimization_needed: data.layers.memory ? 0 : 1,
      memory_usage_status: 'normal',
      recommendations: [
        data.details.memory.message,
        data.details.redis.message
      ]
    };
  } catch (error) {
    console.error('API: 獲取緩存健康狀態失敗:', error);
    throw error;
  }
};

/**
 * 獲取提示詞緩存詳細統計
 */
export const getPromptCacheDetailedStatistics = async (): Promise<PromptCacheDetailedStats> => {
  console.log('API: 獲取提示詞緩存詳細統計...');
  try {
    const response = await apiClient.get<PromptCacheDetailedStats>('/cache/prompt-cache/detailed');
    console.log('API: 提示詞緩存詳細統計獲取成功:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: 獲取提示詞緩存詳細統計失敗:', error);
    throw error;
  }
};

/**
 * 優化所有提示詞緩存
 */
export const optimizeAllPromptCaches = async (): Promise<PromptCacheOptimizationResult> => {
  console.log('API: 優化所有提示詞緩存...');
  try {
    const response = await apiClient.post<PromptCacheOptimizationResult>('/cache/prompt-cache/optimize-all');
    console.log('API: 提示詞緩存優化成功:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: 提示詞緩存優化失敗:', error);
    throw error;
  }
};

/**
 * 緩存管理統一API對象
 */
export const CacheAPI = {
  // 新API
  getCacheSummary,
  getCacheNamespaces,
  clearNamespaceCache,
  
  // 舊API（兼容層）
  getCacheStatistics,
  clearCache,
  cleanupExpiredCaches,
  getCacheHealth,
  getPromptCacheDetailedStatistics,
  optimizeAllPromptCaches
};

export default CacheAPI;