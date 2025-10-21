/**
 * 聚類服務
 * 提供文檔動態聚類的前端API調用
 */

import { apiClient } from './apiClient';
import { 
  ClusteringJobStatus, 
  ClusterSummary, 
  Document 
} from '../types/apiTypes';

/**
 * 手動觸發聚類
 * @param forceRecluster 是否強制重新聚類已聚類的文檔
 * @returns 聚類任務狀態
 */
export const triggerClustering = async (
  forceRecluster: boolean = false
): Promise<ClusteringJobStatus> => {
  const response = await apiClient.post<ClusteringJobStatus>(
    '/clustering/trigger',
    null,
    { params: { force_recluster: forceRecluster } }
  );
  return response.data;
};

/**
 * 手動觸發階層聚類 (兩級結構)
 * 
 * 階層1 (Level 0 - 大類): 超商、帳單、食品等
 * 階層2 (Level 1 - 細分類): 7-11、全家、水費、電費等
 * 
 * @param forceRecluster 是否強制重新聚類已聚類的文檔
 * @returns 聚類任務狀態
 */
export const triggerHierarchicalClustering = async (
  forceRecluster: boolean = false
): Promise<ClusteringJobStatus> => {
  const response = await apiClient.post<ClusteringJobStatus>(
    '/clustering/trigger-hierarchical',
    null,
    { params: { force_recluster: forceRecluster } }
  );
  return response.data;
};

/**
 * 獲取當前用戶的最新聚類任務狀態
 * @returns 最新的聚類任務狀態,如果不存在則返回null
 */
export const getClusteringStatus = async (): Promise<ClusteringJobStatus | null> => {
  try {
    const response = await apiClient.get<ClusteringJobStatus>('/clustering/status');
    return response.data;
  } catch (error: any) {
    // 如果沒有任務記錄,返回null而不是拋出錯誤
    if (error.response?.status === 404) {
      return null;
    }
    throw error;
  }
};

/**
 * 獲取用戶的所有聚類列表
 * @param level 過濾層級 (null=全部, 0=僅大類, 1=僅子類)
 * @param includeSubclusters 是否包含子聚類的完整信息
 * @returns 聚類摘要列表
 */
export const getUserClusters = async (
  level?: number | null,
  includeSubclusters: boolean = true
): Promise<ClusterSummary[]> => {
  const params: any = { include_subclusters: includeSubclusters };
  if (level !== undefined && level !== null) {
    params.level = level;
  }
  const response = await apiClient.get<ClusterSummary[]>(
    '/clustering/clusters',
    { params }
  );
  return response.data;
};

/**
 * 獲取特定聚類中的所有文檔
 * @param clusterId 聚類ID
 * @returns 文檔列表
 */
export const getClusterDocuments = async (
  clusterId: string
): Promise<Document[]> => {
  const response = await apiClient.get<Document[]>(
    `/clustering/clusters/${clusterId}/documents`
  );
  return response.data;
};

/**
 * 刪除聚類
 * @param clusterId 聚類ID
 * @returns 刪除結果
 */
export const deleteCluster = async (
  clusterId: string
): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.delete(
    `/clustering/clusters/${clusterId}`
  );
  return response.data;
};

/**
 * 獲取結構化的聚類樹（三層結構）
 * @returns 結構化聚類樹
 */
export const getClustersTree = async (): Promise<{
  main_clusters: ClusterSummary[];
  small_clusters: ClusterSummary[];
  unclustered_count: number;
  total_clusters: number;
}> => {
  const response = await apiClient.get('/clustering/tree');
  return response.data;
};

/**
 * 獲取聚類統計信息
 * @returns 統計信息對象
 */
export const getClusteringStatistics = async (): Promise<{
  total_clusters: number;
  pending_documents: number;
  clustered_documents: number;
  excluded_documents: number;
  total_documents: number;
  clustering_coverage: number;
}> => {
  const response = await apiClient.get('/clustering/statistics');
  return response.data;
};

/**
 * 輪詢聚類狀態
 * 用於監控聚類任務的進度
 * @param jobId 任務ID (可選,如果不提供則獲取最新任務)
 * @param onUpdate 狀態更新回調函數
 * @param intervalMs 輪詢間隔(毫秒),默認2000ms
 * @returns 停止輪詢的函數
 */
export const pollClusteringStatus = (
  onUpdate: (status: ClusteringJobStatus | null) => void,
  intervalMs: number = 2000
): (() => void) => {
  let intervalId: NodeJS.Timeout;
  let isPolling = true;

  const poll = async () => {
    if (!isPolling) return;

    try {
      const status = await getClusteringStatus();
      onUpdate(status);

      // 如果任務已完成或失敗,停止輪詢
      if (status && (status.status === 'completed' || status.status === 'failed')) {
        stopPolling();
      }
    } catch (error) {
      console.error('輪詢聚類狀態失敗:', error);
      // 發生錯誤時也通知回調
      onUpdate(null);
    }
  };

  const stopPolling = () => {
    isPolling = false;
    if (intervalId) {
      clearInterval(intervalId);
    }
  };

  // 立即執行一次
  poll();

  // 設置定期輪詢
  intervalId = setInterval(poll, intervalMs);

  // 返回停止輪詢的函數
  return stopPolling;
};

export default {
  triggerClustering,
  triggerHierarchicalClustering,
  getClusteringStatus,
  getUserClusters,
  getClusterDocuments,
  deleteCluster,
  getClustersTree,
  getClusteringStatistics,
  pollClusteringStatus,
};

