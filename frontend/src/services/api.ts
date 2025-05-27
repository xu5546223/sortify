import axios from 'axios';

// 從環境變數讀取 API 基礎 URL，若無則使用預設值
const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 更新的請求攔截器 - 支援新的認證要求
apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('authToken');
  
  // 定義需要認證的端點模式
  const authRequiredEndpoints = [
    '/vector-db/',
    '/embedding/',
    '/unified-ai/',
    '/documents/',
    '/dashboard/',
    '/logs/',
    '/auth/users/' // 用戶相關端點需要認證
  ];
  
  // 檢查當前請求是否需要認證
  const requiresAuth = authRequiredEndpoints.some(endpoint => 
    config.url?.includes(endpoint)
  );
  
  if (token) {
    // 確保 config.headers 存在，如果不存在則初始化
    if (!config.headers) {
      config.headers = {} as import('axios').AxiosRequestHeaders;
    }
    config.headers.Authorization = `Bearer ${token}`;
  } else if (requiresAuth) {
    // 如果需要認證但沒有token，記錄警告
    console.warn('API request requires authentication but no token found:', config.url);
  }

  // 如果請求的 data 是 FormData 實例，則刪除 Content-Type header，
  // 讓 axios 自動設置為 multipart/form-data 並包含正確的 boundary。
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  
  return config;
});

// 改進的回應攔截器 - 統一錯誤處理
apiClient.interceptors.response.use(
  response => response,
  error => {
    // 處理認證錯誤
    if (error.response?.status === 401) {
      console.warn('Authentication failed, removing token and redirecting to login');
      localStorage.removeItem('authToken');
      // 可以在此處添加重定向邏輯
      // window.location.href = '/login';
    }
    
    // 處理權限錯誤
    if (error.response?.status === 403) {
      console.error('Access denied:', error.response.data);
    }
    
    // 統一錯誤格式處理
    const errorMessage = error.response?.data?.detail || error.message || '請求發生錯誤';
    console.error('API Error:', {
      status: error.response?.status,
      message: errorMessage,
      url: error.config?.url
    });
    
    return Promise.reject(error);
  }
);

// --- 共用類型定義 ---
export type LogLevel = 'info' | 'warning' | 'error' | 'debug';

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface LogEntry {
  id: string;
  timestamp: string; // Should be ISO 8601 string from backend
  level: LogLevel;
  message: string;
  source?: string;
}

// BasicResponse 接口定義
export interface BasicResponse {
  success: boolean;
  message: string;
  details?: any; // 保持泛用性，或者為特定情況創建更具體的 details 類型
  [key: string]: any; 
}

// 新增批量刪除響應的詳細類型
export interface BatchDeleteErrorDetail {
  id: string;      // 對應後端的 uuid.UUID，前端通常作為 string
  status: string;  // "deleted", "not_found", "forbidden", "error"
  message?: string;
}

export interface BatchDeleteDocumentsApiResponse {
  success: boolean;
  message: string;
  processed_count: number;
  success_count: number;
  details: BatchDeleteErrorDetail[];
}

// --- Dashboard 相關介面 ---
export interface Activity {
  id: string; // Corresponds to ActivityItem.id (UUID converted to string)
  timestamp: string; // Corresponds to ActivityItem.timestamp (datetime formatted to string)
  type: 'upload' | 'analysis' | 'query' | 'error' | 'login' | 'system' | 'general_log' | string; // Extended to handle more types from backend's activity_type
  description: string; // Corresponds to ActivityItem.summary
}

export interface Stats { // Frontend Stats interface
  totalDocs: number; // Corresponds to SystemStats.total_documents
  analyzedDocs: number; // Corresponds to SystemStats.processed_documents
  activeConnections: number; // Corresponds to SystemStats.active_connections
}

// Helper type for backend's SystemStats
interface BackendSystemStats {
  total_documents: number;
  processed_documents: number;
  pending_documents: number;
  total_registered_devices: number;
  active_connections: number;
  total_storage_used_mb: number;
  error_logs_last_24h: number;
}

// Helper type for backend's ActivityItem
interface BackendActivityItem {
  id: string; // UUID as string
  timestamp: string; // ISO datetime string
  activity_type: string;
  summary: string;
  user_id?: string | null;
  device_id?: string | null;
  related_item_id?: string | null;
  details?: Record<string, any> | null;
}

// Helper type for backend's RecentActivities
interface BackendRecentActivities {
  activities: BackendActivityItem[];
  total_count: number;
  limit: number;
  skip: number;
}

// --- ConnectionPage 相關介面 ---
export interface ConnectedUser {
  id: string; // Corresponds to device_id
  name: string; // Corresponds to device_name
  device: string; // Corresponds to device_type or a descriptive string from user_agent
  connectionTime: string; // Corresponds to first_connected_at (formatted)
}

export interface ConnectionInfo {
  qrCode: string; // Base64 PNG or SVG string
  connectionCode: string;
}

export type TunnelStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export default apiClient;

// --- ConnectionPage 相關 API 函數 ---
const getConnectionInfo = async (): Promise<ConnectionInfo> => {
  console.log('API: Fetching connection info...');
  try {
    const response = await apiClient.get<ConnectionInfo>('/system/connection-info');
    console.log('API: Connection info fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to fetch connection info:', error);
    throw error;
  }
};

const getTunnelStatus = async (): Promise<TunnelStatus> => {
  console.log('API: Fetching tunnel status...');
  try {
    const response = await apiClient.get<TunnelStatus>('/system/tunnel-status');
    console.log('API: Tunnel status fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to fetch tunnel status:', error);
    throw error;
  }
};

// Backend's ConnectedDevice model structure:
interface BackendConnectedDevice {
  device_id: string;
  device_name?: string | null;
  device_type?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  first_connected_at: string; 
  last_active_at: string;   
  is_active: boolean;
  user_id?: string | null;
}

const getConnectedUsersList = async (): Promise<ConnectedUser[]> => {
  console.log('API: Fetching connected users list...');
  try {
    const response = await apiClient.get<BackendConnectedDevice[]>('/auth/users/'); // 更新端點路徑
    console.log('API: Connected users list fetched (raw):', response.data);
    const mappedUsers: ConnectedUser[] = response.data.map(device => ({
      id: device.device_id,
      name: device.device_name || 'Unknown Device',
      device: device.device_type || device.user_agent || 'N/A',
      connectionTime: new Date(device.first_connected_at).toLocaleString(),
    }));
    console.log('API: Connected users list mapped:', mappedUsers);
    return mappedUsers;
  } catch (error) {
    console.error('API: Failed to fetch connected users list:', error);
    throw error;
  }
};

const refreshConnectionInfo = async (): Promise<ConnectionInfo> => {
  console.log('API: Refreshing connection info...');
  try {
    const response = await apiClient.post<ConnectionInfo>('/system/connection-info/refresh');
    console.log('API: Connection info refreshed:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to refresh connection info:', error);
    throw error;
  }
};

const disconnectUser = async (userId: string): Promise<{ success: boolean }> => {
  console.log(`API: Disconnecting user ${userId}...`);
  try {
    await apiClient.post<BackendConnectedDevice>(`/auth/users/${userId}/disconnect`); // 更新端點路徑
    return { success: true };
  } catch (error: any) {
    console.error(`API: Failed to disconnect user ${userId}:`, error);
    throw error;
  }
};

// Export these functions as a namespace object
export const ConnectionAPI = {
  getConnectionInfo,
  getTunnelStatus,
  getConnectedUsersList,
  refreshConnectionInfo,
  disconnectUser
};

// --- Dashboard API 函數 ---
export const getDashboardStats = async (): Promise<Stats> => {
  console.log('API: Fetching dashboard stats...');
  try {
    const response = await apiClient.get<BackendSystemStats>('/dashboard/stats');
    console.log('API: Dashboard stats fetched (raw):', response.data);
    // Map BackendSystemStats to frontend's Stats
    const frontendStats: Stats = {
      totalDocs: response.data.total_documents,
      analyzedDocs: response.data.processed_documents,
      activeConnections: response.data.active_connections,
    };
    console.log('API: Dashboard stats mapped:', frontendStats);
    return frontendStats;
  } catch (error) {
    console.error('API: Failed to fetch dashboard stats:', error);
    throw error;
  }
};

export const getRecentActivities = async (): Promise<Activity[]> => {
  console.log('API: Fetching recent activities...');
  try {
    const response = await apiClient.get<BackendRecentActivities>('/dashboard/recent-activities');
    console.log('API: Recent activities fetched (raw):', response.data);

    // Map BackendActivityItem to frontend's Activity
    const mappedActivities: Activity[] = response.data.activities.map(item => {
      // Basic mapping for activity_type to frontend's enum-like type
      let frontendActivityType: Activity['type'] = item.activity_type.toLowerCase();
      if (item.activity_type.includes('upload')) frontendActivityType = 'upload';
      else if (item.activity_type.includes('analysis') || item.activity_type.includes('analyze')) frontendActivityType = 'analysis';
      else if (item.activity_type.includes('query') || item.activity_type.includes('search')) frontendActivityType = 'query';
      else if (item.activity_type.includes('error')) frontendActivityType = 'error';
      else if (item.activity_type.includes('login')) frontendActivityType = 'login';

      const knownTypes: Activity['type'][] = ['upload', 'analysis', 'query', 'error', 'login', 'system'];
      if (!knownTypes.includes(frontendActivityType as any) && !item.activity_type.toLowerCase().includes('log')) {
          frontendActivityType = item.activity_type;
      }

      return {
        id: item.id, // Already a string (UUID)
        timestamp: new Date(item.timestamp).toLocaleString(), // Format datetime
        type: frontendActivityType,
        description: item.summary,
      };
    });
    console.log('API: Recent activities mapped:', mappedActivities);
    return mappedActivities;
  } catch (error) {
    console.error('API: Failed to fetch recent activities:', error);
    throw error;
  }
};

// --- 系統設定相關介面與 API ---
export interface AIServiceSettings {
  provider?: string | null;
  model?: string | null;
  temperature?: number | null;
  is_api_key_configured?: boolean | null;
  apiKey?: string | null; // Only for sending updates, not for GET
  force_stable_model?: boolean | null;
  ensure_chinese_output?: boolean | null;
  max_output_tokens?: number | null; // 新增字段
}

export interface AIServiceSettingsUpdate {
  provider?: string;
  model?: string | null;
  apiKey?: string | null;
  temperature?: number | null;
  force_stable_model?: boolean | null;
  ensure_chinese_output?: boolean | null;
  max_output_tokens?: number | null; // 新增字段
}

export interface DatabaseSettings {
  uri?: string | null;
  dbName?: string | null;
  trigger_content_processing?: boolean | null;
  ai_force_stable_model?: boolean | null;
  ai_ensure_chinese_output?: boolean | null;
}

export interface SettingsData {
  aiService?: AIServiceSettings;
  database?: DatabaseSettings;
  autoConnect?: boolean | null;
  autoSync?: boolean | null;
}

export interface UpdatableSettingsPayload {
    aiService?: AIServiceSettingsUpdate;
    database?: DatabaseSettings;
    autoConnect?: boolean | null;
    autoSync?: boolean | null;
}

export const getSettings = async (): Promise<SettingsData> => {
  console.log('API: Fetching settings...');
  try {
    const response = await apiClient.get<SettingsData>('/system/settings');
    console.log('API: Settings fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to fetch settings:', error);
    throw error;
  }
};

export const updateSettings = async (newSettings: UpdatableSettingsPayload): Promise<SettingsData> => {
  console.log('API: Updating settings...', newSettings);
  try {
    const response = await apiClient.put<SettingsData>('/system/settings', newSettings);
    console.log('API: Settings updated:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to update settings:', error);
    throw error;
  }
};

// --- System Settings 相關介面 ---
export interface TestDBConnectionRequest {
  uri: string;
  db_name: string;
}

export interface TestDBConnectionResponse {
  success: boolean;
  message: string;
  error_details?: string;
}

export const testDBConnection = async (payload: TestDBConnectionRequest): Promise<TestDBConnectionResponse> => {
  console.log('API: Testing DB connection...', payload);
  try {
    const response = await apiClient.post<TestDBConnectionResponse>('/system/test-db-connection', payload);
    console.log('API: DB connection test response:', response.data);
    return response.data;
  } catch (error: any) {
    console.error('API: Failed to test DB connection:', error.response?.data || error.message);
    if (error.response?.data && typeof error.response.data.success === 'boolean' && typeof error.response.data.message === 'string') {
      return error.response.data as TestDBConnectionResponse;
    }
    const errorMessage = error.response?.data?.detail || 
                         (error.response?.data?.message && typeof error.response?.data?.success === 'boolean' ? error.response.data.message : null) || 
                         (error.isAxiosError && error.message) || 
                         "測試資料庫連線時發生未知網路錯誤";
    const errorDetails = typeof error.response?.data?.detail === 'string' ? error.response.data.detail : undefined;

    return {
      success: false,
      message: errorMessage,
      error_details: errorDetails || (error.isAxiosError ? error.message : String(error)),
    };
  }
};

// --- Document Types ---
export type DocumentStatus =
  | "uploaded"
  | "pending_extraction"
  | "text_extracted"
  | "extraction_failed"
  | "pending_analysis"
  | "analyzing"
  | "analysis_completed"
  | "analysis_failed"
  | "processing_error"
  | "completed";

export interface AITextAnalysisIntermediateStep {
  potential_field: string;
  text_fragment?: string | null;
  reasoning: string;
}

export interface AITextKeyInformation {
  main_topic_or_title?: string | null;
  text_date?: string | null;
  author_or_source?: string | null;
  language?: string | null;
  key_findings?: string[];
  conclusions?: string[];
  recommendations?: string[];
  involved_entities?: string[];
  sender?: string | null;
  main_purpose?: string | null;
  requested_action?: string | null;
  central_idea?: string | null;
  main_characters_or_subjects?: string[];
  emotional_tone?: string | null;
  keywords?: string[];
  common_feature_of_list_items?: string | null;
  summary_of_data_points?: string | null;
  other_specific_text_info?: Record<string, any> | null;
}

export interface AITextAnalysisOutput {
  initial_summary: string;
  content_type: string;
  intermediate_analysis: AITextAnalysisIntermediateStep[] | Record<string, any>;
  key_information: AITextKeyInformation | Record<string, any>;
  model_used?: string | null;
  error_message?: string | null;
}

export interface DocumentAnalysis {
  tokens_used?: number | null;
  analysis_started_at?: string | null;
  analysis_completed_at?: string | null;
  error_message?: string | null;
  analysis_model_used?: string | null;
  ai_analysis_output?: Record<string, any> | null; 
}

export interface Document {
  id: string; // Backend Pydantic model uses 'id' (UUID)
  filename: string;
  file_type?: string | null;
  size?: number | null;
  uploader_device_id?: string | null;
  owner_id: string; // UUID, 文件擁有者的用戶ID
  tags?: string[];
  metadata?: Record<string, any>;
  created_at: string;
  updated_at: string;
  status: DocumentStatus;
  vector_status?: "not_vectorized" | "processing" | "vectorized" | "failed";
  file_path?: string | null;
  extracted_text?: string | null;
  text_extraction_completed_at?: string | null;
  analysis?: DocumentAnalysis | null;
  error_details?: string | null;
}

export const getDocuments = async (
    searchTerm?: string,
    status?: DocumentStatus | 'all',
    tagsInclude?: string[],
    sortBy?: keyof Document, 
    sortOrder?: 'asc' | 'desc',
    skip: number = 0,
    limit: number = 20
): Promise<{ documents: Document[], totalCount: number }> => {
    console.log(`API: Fetching documents... Search: ${searchTerm}, Status: ${status}, Tags: ${tagsInclude}, SortBy: ${sortBy} ${sortOrder}, Skip: ${skip}, Limit: ${limit}`);
    try {
        const params: Record<string, any> = {
            skip: skip,
            limit: limit
        };
        if (searchTerm) {
            params.filename_contains = searchTerm;
        }
        if (status && status !== 'all') {
            params.status = status;
        }
        if (tagsInclude && tagsInclude.length > 0) {
            params.tags_include = tagsInclude;
        }
        if (sortBy) {
            params.sort_by = sortBy; 
            if (sortOrder) {
                params.sort_order = sortOrder; 
            }
        }

        const response = await apiClient.get<{ items?: Document[], total?: number }>('/documents/', { params });
        console.log('API: Documents fetched (raw response):', response.data);

        // Temporary log to check IDs
        if (response.data?.items) {
          response.data.items.forEach((doc, index) => {
            console.log(`Document ${index} ID:`, doc.id, typeof doc.id);
            if (doc.id === undefined) {
              console.warn(`Warning: Document at index ${index} has an undefined ID. Document data:`, doc);
            }
          });
        }

        return {
            documents: response.data?.items || [],
            totalCount: response.data?.total || 0
        };

    } catch (error) {
        console.error('API: Failed to fetch documents:', error);
        throw error; 
    }
};

// 新增缺失的類型定義
export interface DocumentUpdateRequest {
  filename?: string | null;
  tags?: string[] | null;
  metadata?: Record<string, any> | null;
  trigger_content_processing?: boolean | null;
  ai_force_stable_model?: boolean | null;
  ai_ensure_chinese_output?: boolean | null;
}

export interface TriggerDocumentProcessingOptions {
  trigger_content_processing?: boolean;
  ai_force_stable_model?: boolean;
  ai_ensure_chinese_output?: boolean;
}

export const deleteDocument = async (documentId: string): Promise<BasicResponse> => {
  console.log(`API: Attempting to delete document: ${documentId}`);
  try {
    // 假設後端 DELETE /documents/{document_id} 返回 204 No Content 或 BasicResponse
    // 這裡我們需要確保 apiClient.delete 對 204 的處理符合預期
    // 或者後端應返回 BasicResponse
    const response = await apiClient.delete<BasicResponse>(`/documents/${documentId}`);
    // 如果是 204 No Content, response.data 可能為空，需要處理
    if (response.status === 204) {
      return { success: true, message: "Document deleted successfully." };
    }
    return response.data;
  } catch (error) {
    console.error(`API: Failed to delete document ${documentId}:`, error);
    throw error;
  }
};

// 修改此函數以符合後端 POST /documents/batch-delete
export const deleteDocuments = async (documentIds: string[]): Promise<BatchDeleteDocumentsApiResponse> => {
  console.log(`API: Attempting to batch delete documents with IDs: ${documentIds.join(', ')}`);
  try {
    // 後端期望 document_ids 是 UUID 列表，但前端傳遞 string 列表是常見做法，
    // 後端 Pydantic 模型會嘗試轉換。如果轉換失敗，後端應返回422。
    const response = await apiClient.post<BatchDeleteDocumentsApiResponse>('/documents/batch-delete', {
      document_ids: documentIds 
    });
    return response.data;
  } catch (error) {
    console.error('API: Failed to batch delete documents:', error);
    // 如果需要，可以根據 error.response.data 構造一個符合 BatchDeleteDocumentsApiResponse 的錯誤對象返回
    // 但通常直接拋出讓調用者處理 AxiosError 更常見。
    throw error;
  }
};

// --- Document Upload API ---
export interface UploadDocumentOptions {
  tags?: string[];
}

export const uploadDocument = async (
  file: File,
  options?: UploadDocumentOptions
): Promise<Document> => {
  console.log(`API: Uploading document: ${file.name}, size: ${file.size}, type: ${file.type}`);
  const formData = new FormData();
  formData.append('file', file);

  if (options?.tags && options.tags.length > 0) {
    options.tags.forEach(tag => {
      formData.append('tags', tag);
    });
  }

  try {
    const response = await apiClient.post<Document>('/documents/', formData);
    console.log('API: Document uploaded successfully:', response.data);
    return response.data; 
  } catch (error) {
    console.error('API: Failed to upload document:', error);
    throw error;
  }
};

// --- AI Model 相關 API ---
export const getGoogleAIModels = async (): Promise<string[]> => {
  console.log('API: Fetching Google AI models...');
  try {
    const response = await apiClient.get<string[]>('/system/ai-models/google');
    console.log('API: Google AI models fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to fetch Google AI models:', error);
    throw error;
  }
};

// --- 觸發文件處理 API ---
export const triggerDocumentProcessing = async (documentId: string, options?: TriggerDocumentProcessingOptions): Promise<Document> => {
  console.log(`API: Triggering content processing for document ${documentId} with options:`, options);
  try {
    const payload: DocumentUpdateRequest = { 
      trigger_content_processing: true,
      ai_force_stable_model: options?.ai_force_stable_model,
      ai_ensure_chinese_output: options?.ai_ensure_chinese_output
    };
    const response = await apiClient.patch<Document>(`/documents/${documentId}`, payload);
    console.log('API: Document processing triggered successfully, updated document:', response.data);
    return response.data;
  } catch (error) {
    console.error(`API: Failed to trigger content processing for document ${documentId}:`, error);
    throw error;
  }
};

// --- AI API Key 測試 API ---
export interface TestApiKeyRequest {
  api_key: string;
}

export interface TestApiKeyResponse {
  status: "success" | "error";
  message: string;
  is_valid: boolean;
}

export const testGoogleApiKey = async (apiKey: string): Promise<TestApiKeyResponse> => {
  console.log(`API: Testing Google AI API Key ending with ...${apiKey.slice(-4)}`);
  try {
    const payload: TestApiKeyRequest = { api_key: apiKey };
    const response = await apiClient.post<TestApiKeyResponse>('/system/test-ai-api-key', payload);
    console.log('API: API Key test response:', response.data);
    return response.data;
  } catch (error: any) {
    console.error('API: Failed to test API Key:', error);
    if (axios.isAxiosError(error) && error.response) {
      if (error.response.data && typeof error.response.data.is_valid === 'boolean') {
        return error.response.data as TestApiKeyResponse;
      }
      return {
        status: "error",
        message: error.response.data?.detail || error.message || "測試 API 金鑰時發生未知網路或伺服器錯誤",
        is_valid: false
      };
    }
    return {
      status: "error",
      message: error.message || "測試 API 金鑰時發生未知錯誤",
      is_valid: false
    };
  }
};

// --- LogsPage 相關介面與 API ---
interface BackendLogEntry {
    id: string;
    timestamp: string;
    level: LogLevel;
    message: string;
    source?: string | null;
    module?: string | null;
    function?: string | null;
    user_id?: string | null;
    device_id?: string | null;
    request_id?: string | null;
    details?: Record<string, any> | null;
}

export const getLogs = async (
    filterLevel?: LogLevel | 'all', 
    searchTerm?: string, 
    sortBy: keyof LogEntry = 'timestamp', 
    sortOrder: 'asc' | 'desc' = 'desc' 
): Promise<LogEntry[]> => {
    try {
        const params: Record<string, string> = {};
        
        if (filterLevel && filterLevel !== 'all') {
            params.level = filterLevel;
        }
        
        if (searchTerm && searchTerm.trim()) {
            params.message_contains = searchTerm.trim();
        }

        const response = await apiClient.get('/logs/', { params });
        return response.data.map((log: BackendLogEntry) => ({
            id: log.id,
            timestamp: log.timestamp,
            level: log.level,
            message: log.message,
            source: log.source || undefined,
        }));
    } catch (error) {
        console.error('獲取日誌失敗:', error);
        throw error;
    }
};

// ========================
// 統一AI服務相關接口 (POST /api/v1/unified-ai/*)
// ========================

// 統一AI請求基類
export interface AIRequest {
  task_type?: string; // 任務類型，由系統自動推斷
  model_preference?: string | null; // 模型偏好
  custom_prompt?: string | null; // 自定義提示詞
}

// 統一AI響應基類
export interface AIResponse<T = any> {
  success: boolean;
  content?: T;
  token_usage?: TokenUsage;
  model_used?: string;
  processing_time?: number;
  error_message?: string;
  request_id?: string;
  created_at?: string;
}

// 文本分析請求
export interface AITextAnalysisRequest extends AIRequest {
  text_content: string; // 要分析的文本內容
  analysis_type?: string; // 分析類型 (可選)
}

// 圖片分析請求
export interface AIImageAnalysisRequest extends AIRequest {
  image_data: string; // Base64編碼的圖片數據
  image_mime_type: string; // 圖片MIME類型
  analysis_focus?: string; // 分析重點 (可選)
}

// AI問答請求 (更新後的格式)
export interface AIQARequestUnified extends AIRequest {
  question: string;
  context_limit?: number;
  use_semantic_search?: boolean;
  use_structured_filter?: boolean;
  session_id?: string | null;
  force_stable_model?: boolean | null;
  ensure_chinese_output?: boolean | null;
}

// 查詢重寫請求
export interface QueryRewriteRequest extends AIRequest {
  original_query: string;
  max_rewrites?: number;
  include_intent_analysis?: boolean;
}

// 查詢重寫響應
export interface QueryRewriteResponse {
  original_query: string;
  rewritten_queries: string[];
  extracted_parameters: Record<string, any>;
  intent_analysis?: string | null;
  processing_time?: number;
  model_used?: string;
}

// AI模型信息
export interface AIModelInfo {
  model_id: string;
  display_name: string;
  provider: string;
  supports_images: boolean;
  supports_json_mode: boolean;
  max_input_tokens: number;
  max_output_tokens: number;
  is_available: boolean;
}

// AI系統狀態
export interface AISystemStatus {
  is_ready: boolean;
  current_provider: string;
  available_models: string[];
  api_key_configured: boolean;
  last_health_check?: string;
  error_message?: string;
}

// ========================
// AI問答相關接口 (保持兼容性)
// ========================

// ========================
// 向量數據庫與語義搜索 API (更新後的端點)
// ========================

// 向量數據庫統計信息相關接口
export interface VectorDatabaseStats {
  collection_name: string;
  total_vectors: number;
  vector_dimension: number;
  status: "ready" | "error";
  embedding_model: {
    model_name: string;
    vector_dimension: number;
    device: "cpu" | "cuda";
    model_loaded: boolean;
    cache_available: boolean;
  };
  error?: string;
}

// 語義搜索相關接口
export interface SemanticSearchRequest {
  query: string;
  top_k?: number;
  similarity_threshold?: number;
  filter_conditions?: Record<string, any>;
}

export interface SemanticSearchResult {
  document_id: string;
  similarity_score: number;
  summary_text: string;
  metadata?: Record<string, any>;
}

// AI問答相關接口
export interface AIQARequest {
  question: string;
  context_limit?: number;
  use_semantic_search?: boolean;
  use_structured_filter?: boolean;
  session_id?: string | null;
}

export interface QueryRewriteResult {
  original_query: string;
  rewritten_queries: string[];
  extracted_parameters: Record<string, any>;
  intent_analysis?: string | null;
}

// 新增 LLMContextDocument 接口
export interface LLMContextDocument {
  document_id: string;
  content_used: string;
  source_type: string;
}

// 新增 SemanticContextDocument 接口 (與後端對應)
export interface SemanticContextDocument {
  document_id: string;
  summary_or_chunk_text: string;
  similarity_score: number;
  metadata?: Record<string, any> | null;
}

export interface AIQAResponse {
  answer: string;
  source_documents: string[];
  confidence_score?: number | null;
  tokens_used: number;
  processing_time: number;
  query_rewrite_result?: QueryRewriteResult | null;
  semantic_search_contexts?: SemanticContextDocument[] | null; // 新增字段
  llm_context_documents?: LLMContextDocument[] | null; // 新增字段
  session_id?: string | null;
  created_at: string;
}

// 新增：AI問答歷史相關接口
export interface ConversationHistoryItem {
  id: string;
  session_id?: string | null;
  question: string;
  answer: string;
  source_documents: string[];
  confidence_score?: number | null;
  tokens_used: number;
  processing_time: number;
  created_at: string;
}

export interface ConversationHistoryResponse {
  conversations: ConversationHistoryItem[];
  total_count: number;
  limit: number;
  skip: number;
}

// 向量數據庫管理接口
export interface ProcessDocumentToVectorResponse {
  message: string;
  document_id: string;
  status: "processing" | "success" | "failed";
  details?: string;
}

export interface BatchProcessDocumentsRequest {
  document_ids: string[];
}

export interface BatchProcessDocumentsResponse {
  message: string;
  document_count: number;
  status: "processing" | "partial_success" | "failed";
  processed_documents?: string[];
  failed_documents?: string[];
}

export interface InitializeVectorDBResponse {
  message: string;
  vector_dimension: number;
  collection_name: string;
  status: "initialized" | "already_initialized" | "failed";
  details?: string;
}

// 獲取向量數據庫統計信息 (更新端點)
export const getVectorDatabaseStats = async (): Promise<VectorDatabaseStats> => {
  try {
    const response = await apiClient.get('/vector-db/stats'); // 更新端點
    return response.data;
  } catch (error) {
    console.error('獲取向量數據庫統計失敗:', error);
    throw error;
  }
};

// 語義搜索 (更新端點)
export const performSemanticSearch = async (query: string, topK = 10, threshold = 0.7): Promise<SemanticSearchResult[]> => {
  const response = await apiClient.post('/vector-db/semantic-search', { // 更新端點
    query,
    top_k: topK,
    similarity_threshold: threshold
  });
  return response.data;
};

// AI問答 (更新為統一AI服務端點，保持函數名稱以維持向後兼容性)
export const askAIQuestion = async (question: string, session_id?: string): Promise<AIQAResponse> => {
  console.log('API: 調用AI問答 (兼容性包裝)...', { question_length: question?.length });
  try {
    // 將舊格式轉換為新的統一AI請求格式
    const request: AIQARequestUnified = {
      question,
      session_id,
      use_semantic_search: true, // 默認使用語義搜索
      context_limit: 10, // 默認上下文限制
      force_stable_model: true,
      ensure_chinese_output: true
    };
    
    // 調用新的統一AI服務
    const response = await askAIQuestionUnified(request);
    
    // 如果成功，返回內容部分以保持向後兼容
    if ((response.success === undefined || response.success) && response.content) {
      return response.content;
    } else {
      throw new Error(response.error_message || 'AI問答失敗');
    }
  } catch (error) {
    console.error('API: AI問答失敗:', error);
    throw error;
  }
};

// 新增：獲取對話歷史 (更新為統一AI服務端點)
export const getConversationHistory = async (
  limit = 20, 
  skip = 0
): Promise<ConversationHistoryResponse> => {
  console.log('API: 獲取對話歷史...', { limit, skip });
  try {
    // 注意：統一AI服務可能還沒有實現歷史記錄功能
    // 這裡先保持舊的端點，或者實現新的邏輯
    const response = await apiClient.get('/unified-ai/conversation-history', {
      params: { limit, skip }
    });
    return response.data;
  } catch (error) {
    console.error('API: 獲取對話歷史失敗:', error);
    throw error;
  }
};

// 新增：清除對話歷史 (更新為統一AI服務端點)
export const clearConversationHistory = async (): Promise<{ message: string }> => {
  console.log('API: 清除對話歷史...');
  try {
    // 注意：統一AI服務可能還沒有實現歷史記錄功能
    // 這裡先保持舊的端點，或者實現新的邏輯
    const response = await apiClient.delete('/unified-ai/conversation-history');
    return response.data;
  } catch (error) {
    console.error('API: 清除對話歷史失敗:', error);
    throw error;
  }
};

// 處理單個文檔到向量數據庫 (更新端點)
export const processDocumentToVector = async (documentId: string): Promise<ProcessDocumentToVectorResponse> => {
  try {
    const response = await apiClient.post(`/vector-db/process-document/${documentId}`); // 更新端點
    return response.data;
  } catch (error) {
    console.error(`處理文檔 ${documentId} 到向量數據庫失敗:`, error);
    throw error;
  }
};

// 批量處理文檔到向量數據庫 (更新端點和請求格式)
export const batchProcessDocuments = async (documentIds: string[]): Promise<BatchProcessDocumentsResponse> => {
  try {
    const response = await apiClient.post('/vector-db/batch-process', { // 更新端點
      document_ids: documentIds // 更新請求格式
    });
    return response.data;
  } catch (error) {
    console.error('批量處理文檔到向量數據庫失敗:', error);
    throw error;
  }
};

// 從向量數據庫刪除文檔 (更新端點)
export const deleteDocumentFromVectorDB = async (documentId: string): Promise<BasicResponse> => {
  console.log(`API: Deleting document from vector DB: ${documentId}`);
  try {
    const response = await apiClient.delete<BasicResponse>(`/vector-db/document/${documentId}`);
    console.log('API: Document deleted from vector DB:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to delete document from vector DB:', error);
    if (axios.isAxiosError(error) && error.response && error.response.data && typeof error.response.data.success === 'boolean') {
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
    if (axios.isAxiosError(error) && error.response && error.response.data && typeof error.response.data.success === 'boolean') {
      return error.response.data as BasicResponse;
    }
    throw error; 
  }
};

// 初始化向量數據庫 (更新端點)
export const initializeVectorDatabase = async (): Promise<InitializeVectorDBResponse> => {
  try {
    const response = await apiClient.post('/vector-db/initialize'); // 更新端點
    return response.data;
  } catch (error) {
    console.error('初始化向量數據庫失敗:', error);
    throw error;
  }
};

// ========================
// 數據庫連接狀態檢查
// ========================

export interface DatabaseConnectionStatus {
  mongodb: {
    connected: boolean;
    database_name?: string;
    connection_count?: number;
    last_ping?: string;
    error?: string;
  };
  vector_db: {
    connected: boolean;
    collection_name?: string;
    total_vectors?: number;
    status?: string;
    error?: string;
  };
}

// 獲取數據庫連接狀態
export const getDatabaseConnectionStatus = async (): Promise<DatabaseConnectionStatus> => {
  try {
    const vectorStats = await getVectorDatabaseStats();

    return {
      mongodb: {
        connected: true, // 假設 MongoDB 連接正常，因為 API 調用能成功
        database_name: 'sortify_db',
        connection_count: 1,
        last_ping: new Date().toISOString(),
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
        connected: false,
        error: '無法連接到數據庫服務'
      },
      vector_db: {
        connected: false,
        total_vectors: 0,
        status: 'error',
        error: String(error)
      }
    };
  }
}; 

// ========================
// Embedding 模型管理 API (更新後的端點)
// ========================

// 新增：Embedding模型狀態接口
export interface EmbeddingModelStatus {
  model_loaded: boolean;
  model_name?: string | null;
  current_device?: string | null;
  memory_usage?: string | null;
  load_time?: string | null;
  vector_dimension?: number | null;
  status: 'ready' | 'loading' | 'error' | 'not_loaded';
  error_message?: string | null;
  last_updated: string;
}

export interface EmbeddingModelConfig {
  current_model: string;
  available_devices: string[];
  recommended_device: string;
  gpu_info?: {
    device_name: string;
    memory_total: string;
    pytorch_version: string;
    cuda_version?: string;
  } | null;
  model_loaded: boolean;
  current_device: string;
  performance_info?: {
    gpu_performance: string;
    cpu_performance: string;
    recommendation: string;
  } | null;
  model_info?: {
    model_name: string;
    vector_dimension: number;
    model_size?: string;
  } | null;
}

export interface ModelLoadResult {
  message: string;
  status: 'loaded' | 'already_loaded' | 'error';
  model_info: {
    model_name: string;
    model_loaded: boolean;
    device: string;
    vector_dimension: number;
  };
  load_time_info?: string | null;
  error_details?: string | null;
}

export interface ModelUnloadResult {
  message: string;
  status: 'unloaded' | 'not_loaded' | 'error';
  freed_memory?: string | null;
  error_details?: string | null;
}

export interface DeviceConfigResult {
  message: string;
  device_preference: string;
  note: string;
  current_device: string;
  requires_restart?: boolean;
  performance_impact?: string;
}

// 更新的 Embedding 模型 API 函數

// 加載Embedding模型 (更新端點)
export const loadEmbeddingModel = async (): Promise<ModelLoadResult> => {
  const response = await apiClient.post('/embedding/load'); // 更新端點
  return response.data;
};

// 獲取Embedding模型配置 (更新端點)
export const getEmbeddingModelConfig = async (): Promise<EmbeddingModelConfig> => {
  const response = await apiClient.get('/embedding/config'); // 更新端點
  return response.data;
};

// 配置Embedding模型設備 (更新端點)
export const configureEmbeddingModel = async (devicePreference: 'cpu' | 'cuda' | 'auto'): Promise<DeviceConfigResult> => {
  const response = await apiClient.post('/embedding/configure-device', { // 更新端點
    device_preference: devicePreference 
  });
  return response.data;
};

// 新增：獲取Embedding模型狀態
export const getEmbeddingModelStatus = async (): Promise<EmbeddingModelStatus> => {
  const response = await apiClient.get('/embedding/status');
  return response.data;
};

// 新增：卸載Embedding模型
export const unloadEmbeddingModel = async (): Promise<ModelUnloadResult> => {
  const response = await apiClient.post('/embedding/unload');
  return response.data;
};

// ========================
// 統一的API調用包裝器
// ========================

export const apiCall = async <T>(
  operation: () => Promise<T>,
  errorMessage = '操作失敗'
): Promise<T> => {
  try {
    return await operation();
  } catch (error) {
    console.error(errorMessage, error);
    throw error;
  }
};

// ========================
// Token 管理工具
// ========================

export class TokenManager {
  private static TOKEN_KEY = 'authToken';
  
  static setToken(token: string) {
    localStorage.setItem(this.TOKEN_KEY, token);
  }
  
  static getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }
  
  static removeToken() {
    localStorage.removeItem(this.TOKEN_KEY);
  }
  
  static isTokenValid(): boolean {
    const token = this.getToken();
    if (!token) return false;
    
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.exp > Date.now() / 1000;
    } catch {
      return false;
    }
  }
  
  static isTokenExpiringSoon(minutesThreshold = 5): boolean {
    const token = this.getToken();
    if (!token) return true;
    
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const expirationTime = payload.exp * 1000;
      const currentTime = Date.now();
      const threshold = minutesThreshold * 60 * 1000;
      
      return (expirationTime - currentTime) < threshold;
    } catch {
      return true;
    }
  }
} 

// ========================
// 統一AI服務 API函數 (/api/v1/unified-ai/)
// ========================

// 文本分析
export const analyzeTextWithUnifiedAI = async (request: AITextAnalysisRequest): Promise<AIResponse<AITextAnalysisOutput>> => {
  console.log('API: 調用統一AI服務進行文本分析...', { text_length: request.text_content?.length });
  try {
    const response = await apiClient.post<AIResponse<AITextAnalysisOutput>>('/unified-ai/analyze-text', request);
    console.log('API: 文本分析完成:', { success: response.data.success, model_used: response.data.model_used });
    return response.data;
  } catch (error) {
    console.error('API: 文本分析失敗:', error);
    throw error;
  }
};

// 圖片分析
export const analyzeImageWithUnifiedAI = async (request: AIImageAnalysisRequest): Promise<AIResponse<any>> => {
  console.log('API: 調用統一AI服務進行圖片分析...', { image_type: request.image_mime_type });
  try {
    const response = await apiClient.post<AIResponse<any>>('/unified-ai/analyze-image', request);
    console.log('API: 圖片分析完成:', { success: response.data.success, model_used: response.data.model_used });
    return response.data;
  } catch (error) {
    console.error('API: 圖片分析失敗:', error);
    throw error;
  }
};

// AI問答 (使用統一AI服務)
export const askAIQuestionUnified = async (request: AIQARequestUnified): Promise<AIResponse<AIQAResponse>> => {
  console.log('API: 調用統一AI服務進行問答...', { question_length: request.question?.length });
  try {
    // 允許 apiClient.post 返回 AIResponse<AIQAResponse> 或直接的 AIQAResponse
    const response = await apiClient.post<AIResponse<AIQAResponse> | AIQAResponse>('/unified-ai/qa', request);
    console.log('API: AI問答原始響應:', response.data);

    // 檢查返回的 data 是否直接是 AIQAResponse (包含 answer 字段)
    // 或者它是一個包裹了 AIQAResponse 的 AIResponse (包含 content 字段)
    if (response.data && 'answer' in response.data && 'tokens_used' in response.data) {
      // 情況1：後端直接返回了 AIQAResponse
      console.log('API: AI問答完成 (直接返回 AIQAResponse 結構)');
      // 我們需要將其包裝成 AIResponse<AIQAResponse> 以符合函數簽名
      // 並確保兼容性包裝 askAIQuestion 能正確工作
      const directResponse = response.data as AIQAResponse;
      return {
        success: true, // 假設直接返回即成功
        content: directResponse,
        model_used: (directResponse as any).model_used || undefined, // 嘗試獲取 model_used, 後端應考慮加入
        processing_time: directResponse.processing_time || undefined,
        token_usage: { 
          prompt_tokens: 0, // 後端 AIQAResponse 應包含更完整的 TokenUsage
          completion_tokens: directResponse.tokens_used || 0,
          total_tokens: directResponse.tokens_used || 0,
        },
        created_at: directResponse.created_at // AIQAResponse 類型中已有
      };
    } else if (response.data && 'content' in response.data && (response.data as AIResponse<AIQAResponse>).success !== undefined) {
      // 情況2：後端返回了標準的 AIResponse<AIQAResponse> 結構
      const responseObject = response.data as AIResponse<AIQAResponse>;
      console.log('API: AI問答完成 (包裹在 AIResponse 結構中):', { success: responseObject.success, model_used: responseObject.model_used });
      return responseObject;
    } else {
      // 返回結構不符合預期
      console.error('API: AI問答返回了非預期的結構:', response.data);
      throw new Error('AI問答返回了非預期的響應結構');
    }
  } catch (error) {
    console.error('API: AI問答失敗(askAIQuestionUnified):', error);
    // 如果錯誤對象是 AxiosError 且有 response.data，則拋出詳細錯誤
    if (axios.isAxiosError(error) && error.response && error.response.data && error.response.data.detail) {
      throw new Error(error.response.data.detail);
    }
    throw error; // 否則拋出原始錯誤
  }
};

// 查詢重寫
export const rewriteQueryWithUnifiedAI = async (request: QueryRewriteRequest): Promise<AIResponse<QueryRewriteResponse>> => {
  console.log('API: 調用統一AI服務進行查詢重寫...', { query: request.original_query });
  try {
    const response = await apiClient.post<AIResponse<QueryRewriteResponse>>('/unified-ai/rewrite-query', request);
    console.log('API: 查詢重寫完成:', { success: response.data.success, rewrites_count: response.data.content?.rewritten_queries?.length });
    return response.data;
  } catch (error) {
    console.error('API: 查詢重寫失敗:', error);
    throw error;
  }
};

// 獲取可用模型列表
export const getUnifiedAIModels = async (): Promise<AIModelInfo[]> => {
  console.log('API: 獲取統一AI服務可用模型列表...');
  try {
    const response = await apiClient.get<AIModelInfo[]>('/unified-ai/models');
    console.log('API: 模型列表獲取成功:', { count: response.data.length });
    return response.data;
  } catch (error) {
    console.error('API: 獲取模型列表失敗:', error);
    throw error;
  }
};

// 獲取可用提示詞列表
export const getUnifiedAIPrompts = async (): Promise<string[]> => {
  console.log('API: 獲取統一AI服務可用提示詞列表...');
  try {
    const response = await apiClient.get<string[]>('/unified-ai/prompts');
    console.log('API: 提示詞列表獲取成功:', { count: response.data.length });
    return response.data;
  } catch (error) {
    console.error('API: 獲取提示詞列表失敗:', error);
    throw error;
  }
};

// 更新API密鑰
export const updateUnifiedAIApiKey = async (apiKey: string): Promise<{ success: boolean; message: string }> => {
  console.log('API: 更新統一AI服務API密鑰...');
  try {
    const response = await apiClient.post<{ success: boolean; message: string }>('/unified-ai/config/api-key', { api_key: apiKey });
    console.log('API: API密鑰更新結果:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: API密鑰更新失敗:', error);
    throw error;
  }
};

// 獲取AI系統狀態
export const getUnifiedAIStatus = async (): Promise<AISystemStatus> => {
  console.log('API: 獲取統一AI服務狀態...');
  try {
    const response = await apiClient.get<AISystemStatus>('/unified-ai/status');
    console.log('API: AI系統狀態:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: 獲取AI系統狀態失敗:', error);
    throw error;
  }
};

// ========================
// 舊版AI問答 API (保持向後兼容性)
// ========================

// --- 獲取單一文檔詳情 API ---
export const getDocumentById = async (documentId: string): Promise<Document> => {
  console.log(`API: Fetching single document: ${documentId}`);
  try {
    const response = await apiClient.get<Document>(`/documents/${documentId}`);
    console.log('API: Single document fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error(`API: Failed to fetch document ${documentId}:`, error);
    throw error;
  }
};

// --- 批量獲取文檔狀態 API ---
export const getDocumentsByIds = async (documentIds: string[]): Promise<Document[]> => {
  console.log(`API: Fetching documents by IDs:`, documentIds);
  try {
    const promises = documentIds.map(id => getDocumentById(id));
    const results = await Promise.allSettled(promises);
    
    const documents: Document[] = [];
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        documents.push(result.value);
      } else {
        console.warn(`Failed to fetch document ${documentIds[index]}:`, result.reason);
      }
    });
    
    console.log(`API: Successfully fetched ${documents.length}/${documentIds.length} documents`);
    return documents;
  } catch (error) {
    console.error('API: Failed to batch fetch documents:', error);
    throw error;
  }
}; 