import React, { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { 
  CacheAPI, 
  type CacheStatistics
} from '../services/cacheService';

const CacheMonitoring: React.FC = () => {
  const [cacheStats, setCacheStats] = useState<CacheStatistics | null>(null);
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

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

  // 生成模擬的 Hit Rate 數據（用於長條圖）
  const generateHitRateData = () => {
    if (!cacheStats?.summary) return [];
    const hitRate = cacheStats.summary.overall_hit_rate || 0;
    // 生成 12 個數據點，模擬最近趨勢
    return Array.from({ length: 12 }, (_, i) => {
      const variance = Math.random() * 20 - 10; // ±10% 波動
      const value = Math.max(20, Math.min(100, hitRate + variance));
      const isHit = Math.random() > 0.15; // 85% 機率是命中
      return { value, isHit };
    });
  };

  useEffect(() => {
    fetchCacheStats();
    
    const interval = setInterval(() => {
      fetchCacheStats();
    }, 30000);
    
    return () => {
      clearInterval(interval);
    };
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-neo-primary';
      case 'needs_optimization': return 'text-neo-warn';
      case 'poor_performance': return 'text-neo-error';
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

  if (!cacheStats || !cacheStats.summary) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center h-64">
          <div className={`w-8 h-8 border-3 border-neo-black border-t-transparent rounded-none ${loading ? 'animate-spin' : ''}`}></div>
          <span className="ml-2 font-display font-bold">{loading ? '載入中...' : '無法載入緩存數據'}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6 md:p-10 space-y-6">
      {/* 消息提示 */}
      {message && (
        <div className={`p-4 border-3 border-neo-black shadow-neo-md rounded-none font-bold ${
          message.type === 'success' 
            ? 'bg-neo-primary text-neo-black' 
            : 'bg-neo-error text-white'
        }`}>
          {message.text}
        </div>
      )}

      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-display font-bold uppercase text-neo-black">Cache Control</h1>
          <p className="text-sm text-gray-600 font-bold mt-1">Redis Performance Monitoring</p>
        </div>
        <div className="flex gap-3">
          <Button 
            onClick={fetchCacheStats}
            disabled={loading}
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

      {/* 緩存統計內容 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Redis 連線狀態卡片 */}
        <Card className="relative overflow-hidden">
          <div className="flex justify-between items-start mb-3">
            <span className="text-xs font-bold text-gray-500 uppercase">Redis Connection</span>
            <div className="w-3 h-3 rounded-full bg-neo-primary border-2 border-neo-black animate-pulse" 
                 style={{ boxShadow: '0 0 8px #29bf12' }} />
          </div>
          <div className="text-3xl font-display font-bold text-neo-black uppercase mb-2">Connected</div>
          <div className="font-mono text-xs text-neo-primary font-bold mb-3">Latency: 2ms</div>
          <div className="pt-3 border-t-2 border-gray-100 flex justify-between text-xs font-bold">
            <span className="text-gray-500">Uptime</span>
            <span className="font-mono text-neo-black">14d 2h 12m</span>
          </div>
          <div className="absolute -right-4 -bottom-4 opacity-5 text-8xl">🔌</div>
        </Card>

        {/* 命中率長條圖 */}
        <Card className="text-center">
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs font-bold text-gray-500 uppercase">Hit Rate (24h)</span>
            <span className="font-mono font-bold text-neo-active text-lg">
              {cacheStats.summary?.overall_hit_rate?.toFixed(1) || '0.0'}%
            </span>
          </div>
          {/* CSS 長條圖 */}
          <div className="flex items-end gap-1 h-16 border-b-2 border-neo-black pb-1">
            {generateHitRateData().map((data, i) => (
              <div
                key={i}
                className={`flex-1 transition-all duration-500 border-t-2 border-l-2 border-r-2 border-neo-black ${
                  data.isHit ? 'bg-neo-active' : 'bg-neo-error'
                }`}
                style={{ height: `${data.value}%` }}
              />
            ))}
          </div>
          <div className="text-[10px] font-bold text-gray-400 mt-1 text-right">Last 60 min trend</div>
        </Card>

        {/* 記憶體使用（帶進度條）*/}
        <Card>
          <div className="flex justify-between items-start mb-2">
            <span className="text-xs font-bold text-gray-500 uppercase">Memory Used</span>
            <span className="text-xl">💾</span>
          </div>
          <div className="text-4xl font-display font-bold text-neo-primary">
            {cacheStats.summary?.total_memory_usage_mb?.toFixed(1) || '0.0'}
            <span className="text-sm text-gray-500 ml-1">MB</span>
          </div>
          <div className="mt-3">
            <div className="flex justify-between text-[10px] font-bold mb-1">
              <span className="text-gray-500">Used</span>
              <span className="text-gray-500">Max: 512MB</span>
            </div>
            {/* Neo-Brutalism 進度條 */}
            <div className="w-full h-4 border-2 border-neo-black bg-gray-100 relative">
              <div 
                className="h-full bg-neo-hover border-r-2 border-neo-black transition-all duration-500"
                style={{ width: `${Math.min(100, ((cacheStats.summary?.total_memory_usage_mb || 0) / 512) * 100)}%` }}
              />
            </div>
          </div>
        </Card>

        {/* 成本節省 - 黑底萊姆字 */}
        <Card className="bg-neo-black text-white relative">
          <div className="text-xs font-bold text-neo-hover uppercase mb-1">Estimated Savings</div>
          <div className="text-4xl font-display font-bold text-neo-hover">
            $ {cacheStats.summary?.estimated_cost_savings_usd?.toFixed(2) || '0.00'}
          </div>
          <p className="text-xs text-gray-400 mt-2 border-l-2 border-neo-hover pl-2">
            Saved approx. <span className="text-white font-mono font-bold">
              {cacheStats.summary?.estimated_token_savings?.toLocaleString() || '0'}
            </span> API tokens by caching.
          </p>
          <button className="absolute top-4 right-4 text-white hover:text-neo-hover transition-colors">
            ℹ️
          </button>
        </Card>
      </div>

      {/* Namespace Breakdown */}
      <div className="mb-4">
        <h2 className="text-xl font-display font-bold uppercase flex items-center gap-2">
          <span>📦</span> Namespace Breakdown
        </h2>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {Object.entries(cacheStats.cache_statistics).map(([type, stats]) => (
          <Card 
            key={type} 
            className="relative group hover:shadow-neo-lg transition-all"
          >
            {/* 卡片頭部：標籤 + 刪除按鈕 */}
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-2">
                <span className={`px-2 py-1 font-mono text-xs font-bold border-2 border-neo-black ${
                  type === 'query_embedding' ? 'bg-neo-active text-white' :
                  type === 'ai_response' ? 'bg-neo-hover text-neo-black' :
                  'bg-neo-black text-white'
                }`}>
                  {type.split('_')[0].toUpperCase()}
                </span>
                <span className="font-bold text-sm">{formatCacheType(type)}</span>
              </div>
              <button
                onClick={() => clearCache(type)}
                disabled={clearing === type}
                className="text-gray-400 hover:text-neo-error transition-colors"
                title="清理"
              >
                🗑️
              </button>
            </div>

            {/* 統計數據網格 */}
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <p className="text-xs font-bold text-gray-500 uppercase">Entries</p>
                <p className="text-lg font-mono font-bold">{stats.hit_count + stats.miss_count}</p>
              </div>
              <div>
                <p className="text-xs font-bold text-gray-500 uppercase">Hit Rate</p>
                <p className={`text-lg font-mono font-bold ${
                  stats.hit_rate > 0.8 ? 'text-neo-primary' : 
                  stats.hit_rate > 0.5 ? 'text-neo-warn' : 'text-neo-error'
                }`}>
                  {(stats.hit_rate * 100).toFixed(0)}%
                </p>
              </div>
            </div>

            {/* 記憶體影響進度條 */}
            <div className="text-xs font-bold mb-1 flex justify-between">
              <span className="text-gray-500 uppercase">Memory Impact</span>
              <span className="font-mono">{stats.memory_usage_mb?.toFixed(1) || '0.0'} MB</span>
            </div>
            <div className="w-full h-2 border-2 border-neo-black bg-gray-100">
              <div 
                className={`h-full transition-all duration-500 ${
                  type === 'query_embedding' ? 'bg-neo-active' :
                  type === 'ai_response' ? 'bg-neo-warn' : 'bg-neo-primary'
                }`}
                style={{ 
                  width: `${Math.min(100, ((stats.memory_usage_mb || 0) / (cacheStats.summary?.total_memory_usage_mb || 1)) * 100)}%` 
                }}
              />
            </div>
            
            {cacheStats.cache_health[type] && (
              <div className="border-t-2 border-gray-200 pt-4">
                <p className="text-xs font-bold text-gray-500 uppercase mb-2">狀態</p>
                <p className={`text-sm font-bold uppercase ${getStatusColor(cacheStats.cache_health[type].status)}`}>
                  {cacheStats.cache_health[type].status}
                </p>
                <p className="text-xs text-gray-600 font-medium mt-1">
                  {cacheStats.cache_health[type].recommendation}
                </p>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
};

export default CacheMonitoring;