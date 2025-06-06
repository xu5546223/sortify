import { apiClient } from './apiClient';

// 緩存統計介面
export interface CacheStats {
  cache_type: string;
  hit_count: number;
  miss_count: number;
  total_requests: number;
  hit_rate: number;
  memory_usage_mb: number;
  last_updated: string;
}

// 緩存統計總結介面
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
 * 獲取緩存統計資訊
 */
export const getCacheStatistics = async (): Promise<CacheStatistics> => {
  console.log('API: 獲取緩存統計資訊...');
  try {
    const response = await apiClient.get<CacheStatistics>('/cache/statistics');
    console.log('API: 緩存統計資訊獲取成功:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: 獲取緩存統計資訊失敗:', error);
    throw error;
  }
};

/**
 * 清理指定類型的緩存
 * @param cacheType 緩存類型 ('schema', 'system_instruction', 'query_embedding', 'document_content', 'ai_response', 'all')
 */
export const clearCache = async (cacheType: string): Promise<CacheResponse> => {
  console.log(`API: 清理緩存類型: ${cacheType}...`);
  try {
    const response = await apiClient.post<CacheResponse>(`/cache/clear/${cacheType}`);
    console.log('API: 緩存清理成功:', response.data);
    return response.data;
  } catch (error) {
    console.error(`API: 清理緩存 ${cacheType} 失敗:`, error);
    throw error;
  }
};

/**
 * 清理過期的緩存項目
 */
export const cleanupExpiredCaches = async (): Promise<CacheResponse> => {
  console.log('API: 清理過期緩存...');
  try {
    const response = await apiClient.post<CacheResponse>('/cache/cleanup-expired');
    console.log('API: 過期緩存清理成功:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: 清理過期緩存失敗:', error);
    throw error;
  }
};

/**
 * 獲取緩存健康狀態
 */
export const getCacheHealth = async (): Promise<CacheHealth> => {
  console.log('API: 獲取緩存健康狀態...');
  try {
    const response = await apiClient.get<CacheHealth>('/cache/health');
    console.log('API: 緩存健康狀態獲取成功:', response.data);
    return response.data;
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
  getCacheStatistics,
  clearCache,
  cleanupExpiredCaches,
  getCacheHealth,
  getPromptCacheDetailedStatistics,
  optimizeAllPromptCaches
};

export default CacheAPI; 