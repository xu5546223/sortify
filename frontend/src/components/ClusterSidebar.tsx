/**
 * 聚類側邊欄組件 - 三層結構版本
 * 顯示用戶的動態文檔分類：主要分類 / 小型分類 / 未分類
 */

import React, { useState, useEffect } from 'react';
import { ClusterSummary } from '../types/apiTypes';
import { getClustersTree } from '../services/clusteringService';
import { 
  FolderOutlined, 
  FolderOpenOutlined,
  RightOutlined, 
  DownOutlined,
  FileTextOutlined,
  TagOutlined,
  CloseOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  ExclamationCircleOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons';
import { message, Modal } from 'antd';

interface ClusterSidebarProps {
  onClusterSelect: (clusterId: string | null) => void;
  selectedClusterId: string | null;
  onClose?: () => void;
}

interface ClusterTreeData {
  main_clusters: ClusterSummary[];
  small_clusters: ClusterSummary[];
  unclustered_count: number;
  total_clusters: number;
}

const ClusterSidebar: React.FC<ClusterSidebarProps> = ({
  onClusterSelect,
  selectedClusterId,
  onClose
}) => {
  const [treeData, setTreeData] = useState<ClusterTreeData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['main', 'small']) // 默認展開主要和小型分類
  );
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());

  // 獲取聚類樹
  const fetchClustersTree = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getClustersTree();
      setTreeData(data);
    } catch (err) {
      console.error('獲取聚類樹失敗:', err);
      setError('無法載入分類列表');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchClustersTree();
  }, []);

  // 切換區塊展開/收起
  const toggleSectionExpand = (section: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };

  // 切換聚類展開/收起
  const toggleClusterExpand = (clusterId: string) => {
    const newExpanded = new Set(expandedClusters);
    if (newExpanded.has(clusterId)) {
      newExpanded.delete(clusterId);
    } else {
      newExpanded.add(clusterId);
    }
    setExpandedClusters(newExpanded);
  };

  // 選擇聚類
  const handleClusterClick = (clusterId: string) => {
    if (selectedClusterId === clusterId) {
      onClusterSelect(null); // 取消選擇
    } else {
      onClusterSelect(clusterId);
    }
  };

  // 刪除聚類
  const handleDeleteCluster = async (clusterId: string, clusterName: string) => {
    Modal.confirm({
      title: '確認刪除分類',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>確定要刪除分類「{clusterName}」嗎?</p>
          <p className="text-sm text-gray-500 mt-2">
            注意: 這只會刪除分類本身,不會刪除文檔。文檔將變為未分類狀態。
          </p>
        </div>
      ),
      okText: '確認刪除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          const { deleteCluster } = await import('../services/clusteringService');
          await deleteCluster(clusterId);
          message.success('分類已刪除');
          
          if (selectedClusterId === clusterId) {
            onClusterSelect(null);
          }
          
          fetchClustersTree();
        } catch (err: any) {
          console.error('刪除分類失敗:', err);
          message.error(err.response?.data?.detail || '刪除分類失敗');
        }
      },
    });
  };

  // 顯示聚類詳細信息
  const showClusterInfo = (cluster: ClusterSummary) => {
    Modal.info({
      title: cluster.cluster_name,
      icon: <InfoCircleOutlined />,
      width: 600,
      content: (
        <div className="space-y-4">
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">分類ID:</p>
            <p className="text-sm text-gray-600 font-mono bg-gray-100 p-2 rounded">
              {cluster.cluster_id}
            </p>
          </div>
          
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">文檔數量:</p>
            <p className="text-sm text-gray-600">{cluster.document_count} 個文檔</p>
          </div>
          
          {cluster.keywords && cluster.keywords.length > 0 && (
            <div>
              <p className="text-sm font-semibold text-gray-700 mb-2">關鍵詞:</p>
              <div className="flex flex-wrap gap-2">
                {cluster.keywords.map((keyword, index) => (
                  <span
                    key={index}
                    className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-blue-100 text-blue-800"
                  >
                    <TagOutlined className="mr-1" />
                    {keyword}
                  </span>
                ))}
              </div>
            </div>
          )}
          
          {cluster.created_at && (
            <div>
              <p className="text-sm font-semibold text-gray-700 mb-1">創建時間:</p>
              <p className="text-sm text-gray-600">
                {new Date(cluster.created_at).toLocaleString('zh-TW')}
              </p>
            </div>
          )}
        </div>
      ),
      okText: '關閉',
    });
  };

  // 渲染單個聚類
  const renderCluster = (cluster: ClusterSummary, isSmall: boolean = false) => {
              const isExpanded = expandedClusters.has(cluster.cluster_id);
              const isSelected = selectedClusterId === cluster.cluster_id;

              return (
                <div key={cluster.cluster_id} className="group">
                  <div
                    className={`flex items-center px-3 py-2 rounded-lg transition-colors ${
                      isSelected
                        ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300'
                        : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    {/* 展開/收起按鈕 */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleClusterExpand(cluster.cluster_id);
                      }}
                      className="mr-1 p-0.5 hover:bg-gray-200 dark:hover:bg-gray-600 rounded transition-colors"
                    >
                      {isExpanded ? (
                        <DownOutlined className="text-xs" />
                      ) : (
                        <RightOutlined className="text-xs" />
                      )}
                    </button>

                    {/* 聚類信息 */}
                    <div
                      onClick={() => handleClusterClick(cluster.cluster_id)}
                      className="flex-1 flex items-center space-x-2 min-w-0 cursor-pointer"
                    >
            {isExpanded ? (
              <FolderOpenOutlined className="text-sm flex-shrink-0 text-yellow-600" />
            ) : (
              <FolderOutlined className="text-sm flex-shrink-0 text-blue-600" />
            )}
            <span className={`text-sm truncate ${isSmall ? 'text-gray-600' : 'font-medium'}`} title={cluster.cluster_name}>
                        {cluster.cluster_name}
                      </span>
                      <span className="ml-auto text-xs bg-gray-200 dark:bg-gray-600 px-2 py-0.5 rounded-full flex-shrink-0">
                        {cluster.document_count}
                      </span>
                    </div>

          {/* 操作按鈕 */}
                    <div className="flex items-center space-x-1 ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          showClusterInfo(cluster);
                        }}
                        className="p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded transition-colors"
                        title="查看詳情"
                      >
                        <InfoCircleOutlined className="text-xs" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteCluster(cluster.cluster_id, cluster.cluster_name);
                        }}
                        className="p-1 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30 rounded transition-colors"
                        title="刪除分類"
                      >
                        <DeleteOutlined className="text-xs" />
                      </button>
                    </div>
                  </div>

                  {/* 展開的關鍵詞列表 */}
                  {isExpanded && cluster.keywords && cluster.keywords.length > 0 && (
                    <div className="ml-8 mt-1 mb-2 space-y-1">
                      {cluster.keywords.slice(0, 5).map((keyword, index) => (
                        <div
                          key={index}
                          className="flex items-center space-x-1 text-xs text-gray-600 dark:text-gray-400"
                        >
                          <TagOutlined className="text-xs" />
                          <span>{keyword}</span>
                        </div>
                      ))}
                      {cluster.keywords.length > 5 && (
                        <div className="text-xs text-gray-500 dark:text-gray-500 pl-4">
                          還有 {cluster.keywords.length - 5} 個關鍵詞...
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
  };

  // 計算總文檔數
  const totalDocuments = treeData
    ? treeData.main_clusters.reduce((sum, c) => sum + c.document_count, 0) +
      treeData.small_clusters.reduce((sum, c) => sum + c.document_count, 0) +
      treeData.unclustered_count
    : 0;

  return (
    <div className="w-full bg-white dark:bg-gray-800 flex flex-col h-full">
      {/* 標題欄 */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <FolderOutlined className="text-lg text-blue-600 dark:text-blue-400" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            文檔分類
          </h3>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            title="關閉側邊欄"
          >
            <CloseOutlined className="text-base" />
          </button>
        )}
      </div>

      {/* 統計摘要 */}
      <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-600 dark:text-gray-400">總文檔數</span>
          <span className="font-semibold text-gray-900 dark:text-white">{totalDocuments}</span>
        </div>
        <div className="flex items-center justify-between text-sm mt-2">
          <span className="text-gray-600 dark:text-gray-400">總分類數</span>
          <span className="font-semibold text-gray-900 dark:text-white">
            {treeData?.total_clusters || 0}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm mt-2">
          <span className="text-gray-600 dark:text-gray-400">未分類</span>
          <span className="font-semibold text-orange-600 dark:text-orange-400">
            {treeData?.unclustered_count || 0}
          </span>
        </div>
      </div>

      {/* 聚類列表 */}
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        )}

        {error && (
          <div className="p-4 m-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
            <button
              onClick={fetchClustersTree}
              className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
            >
              重試
            </button>
          </div>
        )}

        {!isLoading && !error && treeData && (
          <div className="space-y-2">
            {/* 全部文檔選項 */}
            <button
              onClick={() => onClusterSelect(null)}
              className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors ${
                selectedClusterId === null
                  ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300'
                  : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
              }`}
            >
              <div className="flex items-center space-x-2">
                <FileTextOutlined className="text-base flex-shrink-0" />
                <span className="font-semibold text-sm">全部文檔</span>
                <span className="ml-auto text-xs bg-gray-200 dark:bg-gray-600 px-2 py-0.5 rounded-full">
                  {totalDocuments}
                </span>
              </div>
            </button>

            {/* 主要分類 */}
            {treeData.main_clusters.length > 0 && (
              <div className="mt-4">
                <button
                  onClick={() => toggleSectionExpand('main')}
                  className="w-full flex items-center justify-between px-2 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
                >
                  <span className="flex items-center space-x-1">
                    {expandedSections.has('main') ? (
                      <DownOutlined className="text-xs" />
                    ) : (
                      <RightOutlined className="text-xs" />
                    )}
                    <span>主要分類 ({treeData.main_clusters.length})</span>
                  </span>
                </button>
                
                {expandedSections.has('main') && (
                  <div className="space-y-1 mt-1">
                    {treeData.main_clusters.map(cluster => renderCluster(cluster, false))}
                  </div>
                )}
              </div>
            )}

            {/* 小型分類 */}
            {treeData.small_clusters.length > 0 && (
              <div className="mt-4">
                <button
                  onClick={() => toggleSectionExpand('small')}
                  className="w-full flex items-center justify-between px-2 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
                >
                  <span className="flex items-center space-x-1">
                    {expandedSections.has('small') ? (
                      <DownOutlined className="text-xs" />
                    ) : (
                      <RightOutlined className="text-xs" />
                    )}
                    <span>小型分類 ({treeData.small_clusters.length})</span>
                  </span>
                  <QuestionCircleOutlined 
                    className="text-xs" 
                    title="2個文檔的相似分組"
                  />
                </button>
                
                {expandedSections.has('small') && (
                  <div className="space-y-1 mt-1">
                    {treeData.small_clusters.map(cluster => renderCluster(cluster, true))}
                  </div>
                )}
              </div>
            )}

            {/* 未分類文檔 */}
            {treeData.unclustered_count > 0 && (
              <div className="mt-4">
                <div className="px-3 py-2 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800">
                  <div className="flex items-center space-x-2">
                    <QuestionCircleOutlined className="text-orange-600 dark:text-orange-400" />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-orange-800 dark:text-orange-300">
                        未分類文檔
                      </div>
                      <div className="text-xs text-orange-600 dark:text-orange-400 mt-0.5">
                        {treeData.unclustered_count} 個獨立文檔
                      </div>
                    </div>
                  </div>
                  <p className="text-xs text-orange-700 dark:text-orange-300 mt-2">
                    這些文檔暫時沒有找到相似的群組，上傳更多相似文檔後會自動歸類。
                  </p>
                </div>
              </div>
            )}

            {/* 空狀態 */}
            {treeData.main_clusters.length === 0 && 
             treeData.small_clusters.length === 0 && 
             treeData.unclustered_count === 0 && (
              <div className="p-4 text-center text-gray-500 dark:text-gray-400">
                <FolderOutlined className="text-5xl mx-auto mb-2 opacity-50" />
                <p className="text-sm">尚無文檔</p>
                <p className="text-xs mt-1">上傳文檔後會自動生成分類</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 刷新按鈕 */}
      <div className="p-4 border-t border-gray-200 dark:border-gray-700">
        <button
          onClick={fetchClustersTree}
          disabled={isLoading}
          className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 rounded-lg transition-colors"
        >
          {isLoading ? '載入中...' : '刷新分類'}
        </button>
      </div>
    </div>
  );
};

export default ClusterSidebar;
