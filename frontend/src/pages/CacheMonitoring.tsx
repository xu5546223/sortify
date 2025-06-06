import React, { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { 
  CacheAPI, 
  type CacheStatistics, 
  type PromptCacheDetailedStats,
  type PromptCacheOptimizationResult 
} from '../services/cacheService';

const CacheMonitoring: React.FC = () => {
  const [cacheStats, setCacheStats] = useState<CacheStatistics | null>(null);
  const [promptCacheStats, setPromptCacheStats] = useState<PromptCacheDetailedStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [promptLoading, setPromptLoading] = useState(false);
  const [clearing, setClearing] = useState<string | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [activeTab, setActiveTab] = useState<'general' | 'prompts'>('general');

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 3000);
  };

  const fetchCacheStats = async () => {
    setLoading(true);
    try {
      const data = await CacheAPI.getCacheStatistics();
      setCacheStats(data);
    } catch (error) {
      showMessage('error', '無法獲取緩存統計資訊');
    } finally {
      setLoading(false);
    }
  };

  const fetchPromptCacheStats = async () => {
    setPromptLoading(true);
    try {
      const data = await CacheAPI.getPromptCacheDetailedStatistics();
      setPromptCacheStats(data);
    } catch (error) {
      showMessage('error', '無法獲取提示詞緩存統計資訊');
    } finally {
      setPromptLoading(false);
    }
  };

  const clearCache = async (cacheType: string) => {
    setClearing(cacheType);
    try {
      await CacheAPI.clearCache(cacheType);
      showMessage('success', `已清理 ${cacheType} 緩存`);
      fetchCacheStats();
    } catch (error) {
      showMessage('error', '清理緩存失敗');
    } finally {
      setClearing(null);
    }
  };

  const cleanupExpired = async () => {
    setClearing('expired');
    try {
      await CacheAPI.cleanupExpiredCaches();
      showMessage('success', '已清理過期緩存');
      fetchCacheStats();
    } catch (error) {
      showMessage('error', '清理過期緩存失敗');
    } finally {
      setClearing(null);
    }
  };

  const optimizeAllPrompts = async () => {
    setOptimizing(true);
    try {
      const result = await CacheAPI.optimizeAllPromptCaches();
      showMessage('success', result.message);
      fetchPromptCacheStats();
      fetchCacheStats(); // 也刷新一般緩存統計
    } catch (error) {
      showMessage('error', '優化提示詞緩存失敗');
    } finally {
      setOptimizing(false);
    }
  };

  useEffect(() => {
    fetchCacheStats();
    fetchPromptCacheStats();
    const interval = setInterval(() => {
      fetchCacheStats();
      fetchPromptCacheStats();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-600';
      case 'needs_optimization': return 'text-yellow-600';
      case 'poor_performance': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  const formatCacheType = (type: string) => {
    const typeMap: Record<string, string> = {
      'schema': 'Schema 緩存',
      'system_instruction': '系統指令緩存',
      'query_embedding': '查詢向量緩存',
      'document_content': '文檔內容緩存',
      'ai_response': 'AI 回答緩存',
      'prompt_template': '提示詞模板緩存'
    };
    return typeMap[type] || type;
  };

  const formatPromptType = (type: string) => {
    const typeMap: Record<string, string> = {
      'image_analysis': '圖片分析',
      'text_analysis': '文本分析',
      'query_rewrite': '查詢重寫',
      'answer_generation': '回答生成',
      'mongodb_detail_query_generation': 'MongoDB 查詢生成',
      'document_selection_for_query': '文檔選擇'
    };
    return typeMap[type] || type;
  };

  if (!cacheStats) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center h-64">
          <div className={`w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full ${loading ? 'animate-spin' : ''}`}></div>
          <span className="ml-2">載入中...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* 消息提示 */}
      {message && (
        <div className={`p-4 rounded-md ${message.type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {message.text}
        </div>
      )}

      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">緩存監控</h1>
        <div className="flex space-x-2">
          <Button 
            onClick={() => {
              fetchCacheStats();
              fetchPromptCacheStats();
            }} 
            disabled={loading || promptLoading}
            variant="secondary"
          >
            🔄 刷新
          </Button>
          <Button 
            onClick={cleanupExpired}
            disabled={clearing === 'expired'}
            variant="secondary"
          >
            🗑️ 清理過期
          </Button>
          <Button 
            onClick={() => clearCache('all')}
            disabled={clearing === 'all'}
            variant="danger"
          >
            🗑️ 清理所有
          </Button>
        </div>
      </div>

      {/* 標籤頁 */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('general')}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'general'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            一般緩存
          </button>
          <button
            onClick={() => setActiveTab('prompts')}
            className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'prompts'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            提示詞緩存 🔥
          </button>
        </nav>
      </div>

      {/* 一般緩存內容 */}
      {activeTab === 'general' && (
        <>
          {/* 總體統計 */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card title="總體命中率" className="text-center">
              <div className="text-3xl font-bold text-blue-600">
                {cacheStats.summary.overall_hit_rate.toFixed(1)}%
              </div>
              <p className="text-sm text-gray-600 mt-2">
                {cacheStats.summary.total_hits} / {cacheStats.summary.total_requests} 請求
              </p>
            </Card>

            <Card title="記憶體使用" className="text-center">
              <div className="text-3xl font-bold text-green-600">
                {cacheStats.summary.total_memory_usage_mb.toFixed(1)} MB
              </div>
              <p className="text-sm text-gray-600 mt-2">總緩存記憶體</p>
            </Card>

            <Card title="Token 節省" className="text-center">
              <div className="text-3xl font-bold text-purple-600">
                {cacheStats.summary.estimated_token_savings.toLocaleString()}
              </div>
              <p className="text-sm text-gray-600 mt-2">預估節省的 Token 數量</p>
            </Card>

            <Card title="成本節省" className="text-center">
              <div className="text-3xl font-bold text-orange-600">
                ${cacheStats.summary.estimated_cost_savings_usd.toFixed(4)}
              </div>
              <p className="text-sm text-gray-600 mt-2">預估節省的成本 (USD)</p>
            </Card>
          </div>

          {/* 詳細統計 */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {Object.entries(cacheStats.cache_statistics).map(([type, stats]) => (
              <Card 
                key={type} 
                title={formatCacheType(type)}
                headerActions={
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => clearCache(type)}
                    disabled={clearing === type}
                  >
                    🗑️ 清理
                  </Button>
                }
              >
                <div className="grid grid-cols-2 gap-4 mb-4">
                  <div>
                    <p className="text-sm font-medium text-gray-600">命中率</p>
                    <p className="text-xl font-bold">{(stats.hit_rate * 100).toFixed(1)}%</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-600">記憶體使用</p>
                    <p className="text-xl font-bold">{stats.memory_usage_mb.toFixed(2)} MB</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-600">命中次數</p>
                    <p className="text-xl font-bold">{stats.hit_count}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-600">失效次數</p>
                    <p className="text-xl font-bold">{stats.miss_count}</p>
                  </div>
                </div>
                
                {cacheStats.cache_health[type] && (
                  <div className="border-t pt-4">
                    <p className="text-sm font-medium text-gray-600 mb-1">狀態</p>
                    <p className={`text-sm font-medium ${getStatusColor(cacheStats.cache_health[type].status)}`}>
                      {cacheStats.cache_health[type].status}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {cacheStats.cache_health[type].recommendation}
                    </p>
                  </div>
                )}
              </Card>
            ))}
          </div>
        </>
      )}

      {/* 提示詞緩存內容 */}
      {activeTab === 'prompts' && (
        <>
          {promptCacheStats ? (
            <>
              {/* 提示詞緩存總覽 */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <Card title="總提示詞類型" className="text-center">
                  <div className="text-3xl font-bold text-blue-600">
                    {promptCacheStats.summary.total_prompt_types}
                  </div>
                  <p className="text-sm text-gray-600 mt-2">系統中的提示詞類型</p>
                </Card>

                <Card title="已緩存" className="text-center">
                  <div className="text-3xl font-bold text-green-600">
                    {promptCacheStats.summary.cached_prompt_types}
                  </div>
                  <p className="text-sm text-gray-600 mt-2">
                    {((promptCacheStats.summary.cached_prompt_types / promptCacheStats.summary.total_prompt_types) * 100).toFixed(0)}% 緩存率
                  </p>
                </Card>

                <Card title="Google Context 緩存" className="text-center">
                  <div className="text-3xl font-bold text-purple-600">
                    {promptCacheStats.summary.google_context_cached}
                  </div>
                  <p className="text-sm text-gray-600 mt-2">高效 Context Caching</p>
                </Card>

                <Card title="預估月節省" className="text-center">
                  <div className="text-3xl font-bold text-orange-600">
                    ${promptCacheStats.prompt_cache_statistics.estimated_token_savings.potential_monthly_cost_savings_usd.toFixed(2)}
                  </div>
                  <p className="text-sm text-gray-600 mt-2">USD 成本節省</p>
                </Card>
              </div>

              {/* 優化按鈕 */}
              <div className="flex justify-end">
                <Button 
                  onClick={optimizeAllPrompts}
                  disabled={optimizing}
                  variant="primary"
                >
                  {optimizing ? '🔄 優化中...' : '🚀 優化所有提示詞緩存'}
                </Button>
              </div>

              {/* 提示詞詳細列表 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {Object.entries(promptCacheStats.prompt_types_detail).map(([type, details]) => (
                  <Card 
                    key={type} 
                    title={formatPromptType(type)}
                    className={details.is_cached ? 'border-green-200 bg-green-50' : 'border-gray-200'}
                  >
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-600">狀態</span>
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          details.is_cached 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {details.is_cached ? '✅ 已緩存' : '❌ 未緩存'}
                        </span>
                      </div>

                      {details.description && (
                        <div>
                          <p className="text-sm font-medium text-gray-600">描述</p>
                          <p className="text-sm text-gray-900">{details.description}</p>
                        </div>
                      )}

                      {details.estimated_tokens && (
                        <div>
                          <p className="text-sm font-medium text-gray-600">預估 Token 數</p>
                          <p className="text-sm text-gray-900">{Math.round(details.estimated_tokens).toLocaleString()}</p>
                        </div>
                      )}

                      {details.cache_type && (
                        <div>
                          <p className="text-sm font-medium text-gray-600">緩存類型</p>
                          <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                            details.cache_type === 'google_context' 
                              ? 'bg-purple-100 text-purple-800' 
                              : 'bg-blue-100 text-blue-800'
                          }`}>
                            {details.cache_type === 'google_context' ? '🚀 Google Context' : '💾 本地緩存'}
                          </span>
                        </div>
                      )}

                      {details.cache_created_at && (
                        <div>
                          <p className="text-sm font-medium text-gray-600">創建時間</p>
                          <p className="text-xs text-gray-500">
                            {new Date(details.cache_created_at).toLocaleString('zh-TW')}
                          </p>
                        </div>
                      )}

                      {details.error && (
                        <div className="bg-red-50 border border-red-200 rounded p-2">
                          <p className="text-sm text-red-600">錯誤: {details.error}</p>
                        </div>
                      )}
                    </div>
                  </Card>
                ))}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-64">
              <div className={`w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full ${promptLoading ? 'animate-spin' : ''}`}></div>
              <span className="ml-2">載入提示詞緩存統計中...</span>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default CacheMonitoring; 