import { apiClient } from './apiClient';
import type {
  VectorDatabaseStats,
  SemanticSearchRequest,
  SemanticSearchResult,
  ProcessDocumentToVectorResponse,
  BatchProcessDocumentsRequest,
  BatchProcessDocumentsResponse,
  InitializeVectorDBResponse,
  DatabaseConnectionStatus,
  BasicResponse // For delete operations
} from '../types/apiTypes';
import axios from 'axios'; // For isAxiosError check

// 獲取向量數據庫統計信息
export const getVectorDatabaseStats = async (): Promise<VectorDatabaseStats> => {
  try {
    const response = await apiClient.get<VectorDatabaseStats>('/vector-db/stats');
    return response.data;
  } catch (error) {
    console.error('獲取向量數據庫統計失敗:', error);
    throw error;
  }
};

// 語義搜索 - 更新以支援兩階段混合檢索
export const performSemanticSearch = async (
  query: string, 
  topK = 10, 
  threshold = 0.7, 
  collectionName?: string,
  options?: {
    enableHybridSearch?: boolean;
    enableDiversityOptimization?: boolean;
    searchType?: 'hybrid' | 'summary_only' | 'chunks_only' | 'legacy' | 'rrf_fusion';
    filterConditions?: Record<string, any>;
  }
): Promise<SemanticSearchResult[]> => {
  const requestPayload = {
    query,
    top_k: topK,
    similarity_threshold: threshold,
    collection_name: collectionName,
    // 新增：兩階段混合檢索配置
    enable_hybrid_search: options?.enableHybridSearch ?? true, // 預設啟用
    enable_diversity_optimization: options?.enableDiversityOptimization ?? true,
    search_type: options?.searchType || 'hybrid', // 新增：搜索類型
    filter_conditions: options?.filterConditions
  };

  try {
    const response = await apiClient.post<SemanticSearchResult[]>('/vector-db/semantic-search', requestPayload);
    return response.data;
  } catch (error) {
    console.error('語義搜索失敗:', error);
    throw error;
  }
};

// 新增：簡化的兩階段混合檢索接口
export const performHybridSearch = async (
  query: string, 
  topK = 10, 
  threshold = 0.4,
  searchType: 'hybrid' | 'summary_only' | 'chunks_only' | 'rrf_fusion' = 'hybrid'
): Promise<SemanticSearchResult[]> => {
  return performSemanticSearch(query, topK, threshold, undefined, {
    enableHybridSearch: true,
    enableDiversityOptimization: true,
    searchType
  });
};

// 🚀 新增：RRF 融合檢索接口（終極策略）
export const performRRFSearch = async (
  query: string, 
  topK = 10, 
  threshold = 0.4
): Promise<SemanticSearchResult[]> => {
  return performSemanticSearch(query, topK, threshold, undefined, {
    enableHybridSearch: true,
    enableDiversityOptimization: true,
    searchType: 'rrf_fusion'
  });
};

// 新增：傳統搜索接口（向後兼容）
export const performLegacySearch = async (
  query: string, 
  topK = 10, 
  threshold = 0.7
): Promise<SemanticSearchResult[]> => {
  return performSemanticSearch(query, topK, threshold, undefined, {
    enableHybridSearch: false,
    enableDiversityOptimization: false
  });
};

// 處理單個文檔到向量數據庫
export const processDocumentToVector = async (documentId: string): Promise<ProcessDocumentToVectorResponse> => {
  try {
    const response = await apiClient.post<ProcessDocumentToVectorResponse>(`/vector-db/process-document/${documentId}`);
    return response.data;
  } catch (error) {
    console.error(`處理文檔 ${documentId} 到向量數據庫失敗:`, error);
    throw error;
  }
};

// 批量處理文檔到向量數據庫
export const batchProcessDocuments = async (documentIds: string[]): Promise<BatchProcessDocumentsResponse> => {
  try {
    const response = await apiClient.post<BatchProcessDocumentsResponse>('/vector-db/batch-process', {
      document_ids: documentIds
    });
    return response.data;
  } catch (error) {
    console.error('批量處理文檔到向量數據庫失敗:', error);
    throw error;
  }
};

// 從向量數據庫刪除文檔
export const deleteDocumentFromVectorDB = async (documentId: string): Promise<BasicResponse> => {
  console.log(`API: Deleting document from vector DB: ${documentId}`);
  try {
    const response = await apiClient.delete<BasicResponse>(`/vector-db/document/${documentId}`);
    console.log('API: Document deleted from vector DB:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to delete document from vector DB:', error);
    if (axios.isAxiosError(error) && error.response && error.response.data && typeof (error.response.data as BasicResponse).success === 'boolean') {
      return error.response.data as BasicResponse;
    }
    throw error;
  }
};

// 批量從向量數據庫刪除文檔向量
export const deleteDocumentsFromVectorDB = async (documentIds: string[]): Promise<BasicResponse> => {
  console.log(`API: 準備批量刪除向量，文檔IDs: ${documentIds}`);
  try {
    const response = await apiClient.delete<BasicResponse>('/vector-db/documents', { data: { document_ids: documentIds } });
    console.log('API: 批量刪除向量成功:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: 批量刪除向量失敗:', error);
    if (axios.isAxiosError(error) && error.response && error.response.data && typeof (error.response.data as BasicResponse).success === 'boolean') {
      return error.response.data as BasicResponse;
    }
    throw error; 
  }
};

// 初始化向量數據庫
export const initializeVectorDatabase = async (): Promise<InitializeVectorDBResponse> => {
  try {
    const response = await apiClient.post<InitializeVectorDBResponse>('/vector-db/initialize');
    return response.data;
  } catch (error) {
    console.error('初始化向量數據庫失敗:', error);
    throw error;
  }
};

// 獲取數據庫連接狀態 (moved here as it depends on getVectorDatabaseStats)
export const getDatabaseConnectionStatus = async (): Promise<DatabaseConnectionStatus> => {
  try {
    const vectorStats = await getVectorDatabaseStats(); // Call the function from this service

    return {
      mongodb: {
        connected: true, // Assuming if API is up, MongoDB is connected for now
        database_name: 'sortify_db', // Example, ideally this comes from config or an API call
        connection_count: 1, // Example
        last_ping: new Date().toISOString(), // Example
      },
      vector_db: {
        connected: vectorStats.status === 'ready',
        collection_name: vectorStats.collection_name,
        total_vectors: vectorStats.total_vectors,
        status: vectorStats.status,
        error: vectorStats.error
      }
    };
  } catch (error) {
    console.error('獲取數據庫連接狀態失敗:', error);
    
    return {
      mongodb: {
        connected: false, // Default to false on error
        error: '無法連接到主數據庫服務' // General error message
      },
      vector_db: {
        connected: false,
        total_vectors: 0,
        status: 'error',
        error: String(error) // Error from getVectorDatabaseStats or general
      }
    };
  }
}; 