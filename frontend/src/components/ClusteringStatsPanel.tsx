/**
 * 聚類統計面板組件
 * 顯示聚類的整體統計信息
 */

import React, { useState, useEffect } from 'react';
import { ClusterSummary } from '../types/apiTypes';
import { getUserClusters } from '../services/clusteringService';
import {
  BarChartOutlined,
  FolderOutlined,
  FileTextOutlined,
  TagOutlined,
  RiseOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons';

const ClusteringStatsPanel: React.FC = () => {
  const [clusters, setClusters] = useState<ClusterSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 獲取聚類數據
  const fetchClusters = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const clusterData = await getUserClusters();
      setClusters(clusterData);
    } catch (err) {
      console.error('獲取聚類統計失敗:', err);
      setError('無法載入統計信息');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchClusters();
  }, []);

  // 計算統計數據
  const totalClusters = clusters.length;
  const totalDocuments = clusters.reduce((sum, c) => sum + c.document_count, 0);
  const avgDocsPerCluster = totalClusters > 0 ? Math.round(totalDocuments / totalClusters) : 0;
  
  // 找出最大的聚類
  const largestCluster = clusters.reduce((max, c) => 
    c.document_count > (max?.document_count || 0) ? c : max
  , clusters[0]);

  // 收集所有唯一關鍵詞
  const allKeywords = new Set<string>();
  clusters.forEach(cluster => {
    cluster.keywords?.forEach(kw => allKeywords.add(kw));
  });

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
        <div className="flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
        <div className="text-center text-red-600 dark:text-red-400">
          <ExclamationCircleOutlined className="text-3xl mb-2" />
          <p className="text-sm">{error}</p>
        </div>
      </div>
    );
  }

  if (totalClusters === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
        <div className="text-center text-gray-500 dark:text-gray-400">
          <BarChartOutlined className="text-5xl mb-3 opacity-50" />
          <p className="text-sm font-medium">尚無分類統計</p>
          <p className="text-xs mt-1">執行智能分類後會顯示統計信息</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-4">
      {/* 標題 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <BarChartOutlined className="text-base text-blue-600 dark:text-blue-400" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
            分類統計
          </h3>
        </div>
      </div>

      {/* 統計卡片網格 - 更緊湊 */}
      <div className="grid grid-cols-4 gap-3 mb-3">
        {/* 總分類數 */}
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/30 dark:to-blue-800/30 rounded-lg p-3 border border-blue-200 dark:border-blue-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-blue-600 dark:text-blue-400 font-medium mb-0.5">
                總分類數
              </p>
              <p className="text-xl font-bold text-blue-900 dark:text-blue-100">
                {totalClusters}
              </p>
            </div>
            <FolderOutlined className="text-2xl text-blue-600 dark:text-blue-400 opacity-50" />
          </div>
        </div>

        {/* 已分類文檔 */}
        <div className="bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/30 dark:to-green-800/30 rounded-lg p-3 border border-green-200 dark:border-green-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-green-600 dark:text-green-400 font-medium mb-0.5">
                已分類文檔
              </p>
              <p className="text-xl font-bold text-green-900 dark:text-green-100">
                {totalDocuments}
              </p>
            </div>
            <FileTextOutlined className="text-2xl text-green-600 dark:text-green-400 opacity-50" />
          </div>
        </div>

        {/* 平均每類文檔數 */}
        <div className="bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/30 dark:to-purple-800/30 rounded-lg p-3 border border-purple-200 dark:border-purple-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-purple-600 dark:text-purple-400 font-medium mb-0.5">
                平均每類
              </p>
              <p className="text-xl font-bold text-purple-900 dark:text-purple-100">
                {avgDocsPerCluster}
              </p>
            </div>
            <RiseOutlined className="text-2xl text-purple-600 dark:text-purple-400 opacity-50" />
          </div>
        </div>

        {/* 總關鍵詞數 */}
        <div className="bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/30 dark:to-orange-800/30 rounded-lg p-3 border border-orange-200 dark:border-orange-700">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-orange-600 dark:text-orange-400 font-medium mb-0.5">
                總關鍵詞數
              </p>
              <p className="text-xl font-bold text-orange-900 dark:text-orange-100">
                {allKeywords.size}
              </p>
            </div>
            <TagOutlined className="text-2xl text-orange-600 dark:text-orange-400 opacity-50" />
          </div>
        </div>
      </div>

      {/* 最大分類信息 - 更緊湊 */}
      {largestCluster && (
        <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3 border border-gray-200 dark:border-gray-600">
          <div className="flex items-center justify-between mb-2">
            <div className="flex-1">
              <div className="flex items-center space-x-2">
                <span className="text-xs text-gray-600 dark:text-gray-400">📊 最大分類</span>
                <span className="font-medium text-sm text-gray-900 dark:text-white">
                  {largestCluster.cluster_name}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  ({largestCluster.document_count} 個)
                </span>
              </div>
            </div>
          </div>
          
          {/* 關鍵詞 - 單行顯示 */}
          {largestCluster.keywords && largestCluster.keywords.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {largestCluster.keywords.slice(0, 6).map((keyword, index) => (
                <span
                  key={index}
                  className="px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 rounded-full"
                >
                  {keyword}
                </span>
              ))}
              {largestCluster.keywords.length > 6 && (
                <span className="px-2 py-0.5 text-xs text-gray-500 dark:text-gray-400">
                  +{largestCluster.keywords.length - 6}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ClusteringStatsPanel;

