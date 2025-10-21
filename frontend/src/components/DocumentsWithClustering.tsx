/**
 * 帶聚類功能的文檔視圖包裝組件
 * 在現有 DocumentsPage 基礎上添加聚類側邊欄和控制
 */

import React, { useState, useCallback } from 'react';
import ClusterSidebar from './ClusterSidebar';
import ClusteringControl from './ClusteringControl';
import ClusteringStatsPanel from './ClusteringStatsPanel';
import {
  MenuOutlined,
  CloseOutlined,
  BarChartOutlined,
  FilterOutlined
} from '@ant-design/icons';

interface DocumentsWithClusteringProps {
  // 從父組件傳遞的過濾函數
  onClusterFilterChange: (clusterId: string | null) => void;
  currentClusterId: string | null;
  // 刷新文檔列表的回調
  onRefreshDocuments: () => void;
}

const DocumentsWithClustering: React.FC<DocumentsWithClusteringProps> = ({
  onClusterFilterChange,
  currentClusterId,
  onRefreshDocuments
}) => {
  const [showSidebar, setShowSidebar] = useState(true);
  const [showStatsPanel, setShowStatsPanel] = useState(false);
  const [showControlPanel, setShowControlPanel] = useState(false);

  // 聚類完成後的回調
  const handleClusteringComplete = useCallback(() => {
    // 刷新文檔列表和側邊欄
    onRefreshDocuments();
    // 可以添加成功提示
  }, [onRefreshDocuments]);

  return (
    <>
      {/* 右側：分類和控制面板 */}
      {showSidebar && (
        <div className="w-[420px] min-w-[420px] flex flex-col bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 h-full">
          {/* 聚類側邊欄 */}
          <div className="flex-1 overflow-y-auto border-b border-gray-200 dark:border-gray-700">
            <ClusterSidebar
              onClusterSelect={onClusterFilterChange}
              selectedClusterId={currentClusterId}
              onClose={() => setShowSidebar(false)}
            />
          </div>

          {/* 控制面板區域 */}
          <div className="flex-shrink-0">
            {/* 智能分類按鈕 */}
            <div className="p-3 border-b border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setShowControlPanel(!showControlPanel)}
                className={`w-full px-4 py-2.5 text-sm font-medium rounded-lg transition-colors ${
                  showControlPanel
                    ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300'
                    : 'bg-gradient-to-r from-blue-600 to-purple-600 text-white hover:from-blue-700 hover:to-purple-700'
                }`}
              >
                {showControlPanel ? '隱藏智能分類' : '🤖 智能分類'}
              </button>
            </div>

            {/* 控制面板展開內容 */}
            {showControlPanel && (
              <div className="p-3 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 max-h-[300px] overflow-y-auto">
                <ClusteringControl onClusteringComplete={handleClusteringComplete} />
              </div>
            )}

            {/* 統計面板按鈕 */}
            <div className="p-3 border-b border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setShowStatsPanel(!showStatsPanel)}
                className={`w-full px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  showStatsPanel
                    ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                {showStatsPanel ? '隱藏統計' : '📊 查看統計'}
              </button>
            </div>

            {/* 統計面板展開內容 */}
            {showStatsPanel && (
              <div className="p-3 bg-gray-50 dark:bg-gray-900 max-h-[400px] overflow-y-auto">
                <ClusteringStatsPanel />
              </div>
            )}
          </div>
        </div>
      )}

      {/* 隱藏時顯示展開按鈕 */}
      {!showSidebar && (
        <button
          onClick={() => setShowSidebar(true)}
          className="fixed right-4 bottom-4 p-3 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg transition-colors z-50"
          title="顯示分類面板"
        >
          <MenuOutlined className="text-xl" />
        </button>
      )}
    </>
  );
};

export default DocumentsWithClustering;

