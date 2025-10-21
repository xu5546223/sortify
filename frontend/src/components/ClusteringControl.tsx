/**
 * 聚類控制組件
 * 顯示聚類狀態並提供手動觸發功能
 */

import React, { useState, useEffect } from 'react';
import { Modal } from 'antd';
import { ClusteringJobStatus } from '../types/apiTypes';
import { 
  triggerClustering, 
  getClusteringStatus,
  deleteAllClusters
} from '../services/clusteringService';
import { 
  ThunderboltOutlined, 
  ClockCircleOutlined, 
  CheckCircleOutlined, 
  ExclamationCircleOutlined,
  ReloadOutlined,
  DeleteOutlined
} from '@ant-design/icons';

interface ClusteringControlProps {
  onClusteringComplete?: () => void;
}

const ClusteringControl: React.FC<ClusteringControlProps> = ({ 
  onClusteringComplete 
}) => {
  const [jobStatus, setJobStatus] = useState<ClusteringJobStatus | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showStatus, setShowStatus] = useState(false);

  // 獲取聚類狀態
  const fetchStatus = async () => {
    try {
      const status = await getClusteringStatus();
      setJobStatus(status);
      
      // 如果任務完成,通知父組件
      if (status && status.status === 'completed' && onClusteringComplete) {
        onClusteringComplete();
      }
    } catch (err: any) {
      // 404 表示沒有聚類任務,這是正常情況
      if (err.response?.status !== 404) {
        console.error('獲取聚類狀態失敗:', err);
      }
    }
  };

  // 觸發聚類
  const handleTriggerClustering = async () => {
    setIsTriggering(true);
    setError(null);
    try {
      const result = await triggerClustering();
      // 直接使用返回的結果設置狀態
      setJobStatus(result);
      setShowStatus(true);
      
      // 開始輪詢狀態
      startPolling();
    } catch (err: any) {
      console.error('觸發聚類失敗:', err);
      setError(err.response?.data?.detail || '觸發聚類失敗');
    } finally {
      setIsTriggering(false);
    }
  };

  // 輪詢狀態更新
  const startPolling = () => {
    const pollInterval = setInterval(async () => {
      try {
        const status = await getClusteringStatus();
        setJobStatus(status);
        
        if (status && (status.status === 'completed' || status.status === 'failed')) {
          clearInterval(pollInterval);
          if (status.status === 'completed' && onClusteringComplete) {
            onClusteringComplete();
          }
        }
      } catch (err) {
        clearInterval(pollInterval);
      }
    }, 2000); // 每2秒輪詢一次

    // 最多輪詢5分鐘
    setTimeout(() => clearInterval(pollInterval), 300000);
  };

  // 刪除所有聚類
  const handleDeleteAllClusters = () => {
    Modal.confirm({
      title: '🗑️ 確認刪除所有分類？',
      content: (
        <div className="space-y-2">
          <p>此操作會：</p>
          <ul className="list-disc list-inside text-sm text-gray-600 dark:text-gray-400">
            <li>刪除所有現有的分類</li>
            <li>將所有文檔（包括「未分類」）重置為「待分類」狀態</li>
            <li>清除所有聚類數據</li>
          </ul>
          <p className="text-blue-600 dark:text-blue-400 text-sm mt-2">
            💡 重置後可以重新執行智能分類
          </p>
          <p className="text-red-600 dark:text-red-400 font-semibold mt-3">
            ⚠️ 這是破壞性操作，無法撤銷！
          </p>
        </div>
      ),
      okText: '確認刪除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setIsDeleting(true);
        setError(null);
        try {
          const result = await deleteAllClusters();
          setJobStatus(null);
          setShowStatus(false);
          
          // 通知父組件刷新
          if (onClusteringComplete) {
            onClusteringComplete();
          }
          
          // 顯示成功消息
          Modal.success({
            title: '✅ 刪除成功',
            content: result.message
          });
        } catch (err: any) {
          console.error('刪除所有聚類失敗:', err);
          setError(err.response?.data?.detail || '刪除所有聚類失敗');
          
          Modal.error({
            title: '❌ 刪除失敗',
            content: err.response?.data?.detail || '刪除所有聚類失敗'
          });
        } finally {
          setIsDeleting(false);
        }
      }
    });
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  // 獲取狀態圖標和顏色
  const getStatusIcon = () => {
    if (!jobStatus) return null;

    switch (jobStatus.status) {
      case 'running':
        return <ReloadOutlined spin className="text-lg text-blue-600 dark:text-blue-400" />;
      case 'completed':
        return <CheckCircleOutlined className="text-lg text-green-600 dark:text-green-400" />;
      case 'failed':
        return <ExclamationCircleOutlined className="text-lg text-red-600 dark:text-red-400" />;
      case 'pending':
        return <ClockCircleOutlined className="text-lg text-yellow-600 dark:text-yellow-400" />;
      default:
        return null;
    }
  };

  const getStatusText = () => {
    if (!jobStatus) return '尚未執行聚類';

    switch (jobStatus.status) {
      case 'running':
        return '正在執行聚類...';
      case 'completed':
        return `聚類完成 - 生成 ${jobStatus.clusters_created} 個分類`;
      case 'failed':
        return `聚類失敗: ${jobStatus.error_message || '未知錯誤'}`;
      case 'pending':
        return '聚類任務排隊中...';
      default:
        return '未知狀態';
    }
  };

  const getProgressPercentage = () => {
    if (!jobStatus || jobStatus.total_documents === 0) return 0;
    return Math.round((jobStatus.processed_documents / jobStatus.total_documents) * 100);
  };

  return (
    <div className="space-y-3">
      {/* 按鈕組 */}
      <div className="space-y-2">
        {/* 執行分類按鈕 */}
        <button
          onClick={handleTriggerClustering}
          disabled={isTriggering || jobStatus?.status === 'running'}
          className="w-full flex items-center justify-center space-x-2 px-4 py-2 text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 disabled:from-gray-400 disabled:to-gray-500 rounded-lg transition-all duration-200 shadow-md hover:shadow-lg"
        >
          <ThunderboltOutlined className="text-lg" />
          <span>{isTriggering ? '啟動中...' : '執行智能分類'}</span>
        </button>

        {/* 刪除所有分類按鈕 */}
        <button
          onClick={handleDeleteAllClusters}
          disabled={isDeleting || isTriggering || jobStatus?.status === 'running'}
          className="w-full flex items-center justify-center space-x-2 px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 disabled:bg-gray-100 disabled:text-gray-400 dark:disabled:bg-gray-800 rounded-lg transition-all duration-200 border border-red-200 dark:border-red-800"
        >
          <DeleteOutlined className="text-lg" />
          <span>{isDeleting ? '刪除中...' : '刪除所有分類'}</span>
        </button>
      </div>

      {/* 錯誤提示 */}
      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* 狀態顯示 */}
      {(showStatus || jobStatus) && (
        <div className="p-4 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
          {/* 狀態標題 */}
          <div className="flex items-center space-x-2 mb-3">
            {getStatusIcon()}
            <span className="text-sm font-medium text-gray-900 dark:text-white">
              {getStatusText()}
            </span>
          </div>

          {/* 進度條 (僅在運行時顯示) */}
          {jobStatus?.status === 'running' && jobStatus.total_documents > 0 && (
            <div className="space-y-2">
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-blue-600 dark:bg-blue-500 h-2 transition-all duration-300 ease-out"
                  style={{ width: `${getProgressPercentage()}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
                <span>
                  {jobStatus.processed_documents} / {jobStatus.total_documents} 文檔
                </span>
                <span>{getProgressPercentage()}%</span>
              </div>
            </div>
          )}

          {/* 完成統計 */}
          {jobStatus?.status === 'completed' && (
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div className="p-2 bg-white dark:bg-gray-700 rounded-lg">
                <div className="text-xs text-gray-600 dark:text-gray-400">處理文檔</div>
                <div className="text-lg font-semibold text-gray-900 dark:text-white">
                  {jobStatus.total_documents}
                </div>
              </div>
              <div className="p-2 bg-white dark:bg-gray-700 rounded-lg">
                <div className="text-xs text-gray-600 dark:text-gray-400">生成分類</div>
                <div className="text-lg font-semibold text-gray-900 dark:text-white">
                  {jobStatus.clusters_created}
                </div>
              </div>
            </div>
          )}

          {/* 時間信息 */}
          {jobStatus?.started_at && (
            <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
              開始時間: {new Date(jobStatus.started_at).toLocaleString('zh-TW')}
              {jobStatus.completed_at && (
                <span className="ml-2">
                  · 完成時間: {new Date(jobStatus.completed_at).toLocaleString('zh-TW')}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* 說明文字 */}
      <div className="text-xs text-gray-500 dark:text-gray-400">
        <p>💡 智能分類會自動分析您的文檔並生成動態分類</p>
        <p className="mt-1">建議累積 20 個以上文檔後執行效果更佳</p>
      </div>
    </div>
  );
};

export default ClusteringControl;

