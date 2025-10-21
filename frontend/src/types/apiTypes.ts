export type LogLevel = 'info' | 'warning' | 'error' | 'debug';

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  message: string;
  source?: string;
}

export interface BasicResponse {
  success: boolean;
  message: string;
  details?: any;
  [key: string]: any;
}

export interface BatchDeleteErrorDetail {
  id: string;
  status: string;
  message?: string;
}

export interface BatchDeleteDocumentsApiResponse {
  success: boolean;
  message: string;
  processed_count: number;
  success_count: number;
  details: BatchDeleteErrorDetail[];
}

export interface Activity {
  id: string;
  timestamp: string;
  type: 'upload' | 'analysis' | 'query' | 'error' | 'login' | 'system' | 'general_log' | string;
  description: string;
}

export interface Stats {
  totalDocs: number;
  analyzedDocs: number;
  activeConnections: number;
}

// Helper type for backend's SystemStats
export interface BackendSystemStats { // Exporting as it's used by dashboardService
  total_documents: number;
  processed_documents: number;
  pending_documents: number;
  total_registered_devices: number;
  active_connections: number;
  total_storage_used_mb: number;
  error_logs_last_24h: number;
}

// Helper type for backend's ActivityItem
export interface BackendActivityItem { // Exporting as it's used by dashboardService
  id: string;
  timestamp: string;
  activity_type: string;
  summary: string;
  user_id?: string | null;
  device_id?: string | null;
  related_item_id?: string | null;
  details?: Record<string, any> | null;
}

// Helper type for backend's RecentActivities
export interface BackendRecentActivities { // Exporting as it's used by dashboardService
  activities: BackendActivityItem[];
  total_count: number;
  limit: number;
  skip: number;
}

export interface ConnectedUser {
  id: string;
  name: string;
  device: string;
  connectionTime: string;
}

// Backend's ConnectedDevice model structure:
export interface BackendConnectedDevice { // Exporting as it's used by connectionService
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

export interface ConnectionInfo {
  qrCode: string;
  connectionCode: string;
}

export type TunnelStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface AIServiceSettings {
  provider?: string | null;
  model?: string | null;
  temperature?: number | null;
  is_api_key_configured?: boolean | null;
  ensure_chinese_output?: boolean | null;
  max_output_tokens?: number | null;
  prompt_input_max_length?: number | null;  // 新增: 提示詞最大輸入長度
}

export interface AIServiceSettingsUpdate {
  provider?: string;
  model?: string | null;
  temperature?: number | null;
  ensure_chinese_output?: boolean | null;
  max_output_tokens?: number | null;
  prompt_input_max_length?: number | null;  // 新增: 提示詞最大輸入長度
}

export interface DatabaseSettings {
  uri?: string | null;
  dbName?: string | null;
  trigger_content_processing?: boolean | null;
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

export interface TestDBConnectionRequest {
  uri: string;
  db_name: string;
}

export interface TestDBConnectionResponse {
  success: boolean;
  message: string;
  error_details?: string;
}

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

// ========== 聚類相關類型 ==========

export interface EnrichedDataEntities {
  vendor?: string;
  people?: string[];
  locations?: string[];
  organizations?: string[];
  items?: string[];
  amounts?: Array<{value: number; currency: string; context?: string}>;
  dates?: Array<{date: string; context?: string}>;
}

export interface EnrichedData {
  title?: string;
  summary?: string;
  entities?: EnrichedDataEntities;
  keywords?: string[];
  embedding_generated?: boolean;
}

export interface ClusterInfo {
  cluster_id: string;
  cluster_name: string;
  cluster_confidence: number;
  clustered_at: string;
  clustering_version: string;
}

export type ClusteringStatus = 'pending' | 'clustered' | 'excluded';

export interface ClusterSummary {
  cluster_id: string;
  cluster_name: string;
  document_count: number;
  keywords: string[];
  created_at?: string;
  updated_at?: string;
  
  // 階層結構相關 (用於兩級聚類)
  parent_cluster_id?: string | null;
  level: number; // 0=根層級/大類, 1=子層級/細分類
  subclusters: string[]; // 子聚類ID列表
  subcluster_summaries?: ClusterSummary[] | null; // 子聚類摘要(遞歸結構)
}

export interface ClusteringJobStatus {
  job_id: string;
  owner_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  total_documents: number;
  processed_documents: number;
  clusters_created: number;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  progress_percentage: number;
}

export interface Document {
  id: string;
  filename: string;
  file_type?: string | null;
  size?: number | null;
  uploader_device_id?: string | null;
  owner_id: string;
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
  
  // 新增: 聚類和語義豐富化欄位
  // 注意: raw_text 使用現有的 extracted_text 欄位
  enriched_data?: EnrichedData | null;
  cluster_info?: ClusterInfo | null;
  clustering_status?: ClusteringStatus;
}

export interface DocumentUpdateRequest {
  filename?: string | null;
  tags?: string[] | null;
  metadata?: Record<string, any> | null;
  trigger_content_processing?: boolean | null;
  ai_ensure_chinese_output?: boolean | null;
}

export interface TriggerDocumentProcessingOptions {
  trigger_content_processing?: boolean;
  ai_ensure_chinese_output?: boolean;
}

export interface UploadDocumentOptions {
  tags?: string[];
}

// BackendLogEntry is specific to getLogs, so it can stay with logService.ts or be defined here if preferred globally.
// For now, let's assume it's specific enough for logService.ts
// export interface BackendLogEntry { ... }


// Unified AI Service Types
export interface AIRequest {
  task_type?: string;
  model_preference?: string | null;
  custom_prompt?: string | null;
}

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

export interface AITextAnalysisRequest extends AIRequest {
  text_content: string;
  analysis_type?: string;
}

export interface AIImageAnalysisRequest extends AIRequest {
  image_data: string;
  image_mime_type: string;
  analysis_focus?: string;
}

export interface AIQARequestUnified extends AIRequest {
  question: string;
  context_limit?: number;
  use_semantic_search?: boolean;
  use_structured_filter?: boolean;
  session_id?: string | null;
  conversation_id?: string | null; // 對話ID，用於關聯歷史記憶和上下文
  use_ai_detailed_query?: boolean;
  
  // 新增的用戶可調整參數
  detailed_text_max_length?: number; // 詳細文本最大長度 (1000-20000)
  max_chars_per_doc?: number; // 單文檔字符限制 (500-8000)
  query_rewrite_count?: number; // 查詢重寫數量 (1-8)
  max_documents_for_selection?: number; // 候選文件最大數量 (3-15)
  similarity_threshold?: number; // 相似度閾值 (0.1-0.8)
  ai_selection_limit?: number; // AI選擇文件數量限制 (1-8)
  enable_query_expansion?: boolean; // 啟用查詢擴展
  context_window_overlap?: number; // 上下文窗口重疊比例 (0.0-0.5)
  
  // AI 輸出控制參數（從全域設定中獲取，但也可以在請求中覆蓋）
  ensure_chinese_output?: boolean; // 確保中文輸出
  
  // 工作流控制參數
  skip_classification?: boolean; // 跳過問題分類
  workflow_action?: 'approve_search' | 'skip_search' | 'approve_detail_query' | 'skip_detail_query' | 'confirm_documents'; // 工作流操作 ⭐ 新增兩個
  force_strategy?: string; // 強制使用特定策略
  workflow_step?: string; // 當前工作流步驟
  document_ids?: string[]; // 指定文檔ID列表
}

export interface QueryRewriteRequest extends AIRequest {
  original_query: string;
  max_rewrites?: number;
  include_intent_analysis?: boolean;
}

export interface QueryRewriteResponse {
  original_query: string;
  rewritten_queries: string[];
  extracted_parameters: Record<string, any>;
  intent_analysis?: string | null;
  processing_time?: number;
  model_used?: string;
}

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

export interface AISystemStatus {
  is_ready: boolean;
  current_provider: string;
  available_models: string[];
  api_key_configured: boolean;
  last_health_check?: string;
  error_message?: string;
}

// Vector Database & Semantic Search Types
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

export interface SemanticSearchRequest {
  query: string;
  top_k?: number;
  similarity_threshold?: number;
  filter_conditions?: Record<string, any>;
  collection_name?: string;
  
  // 兩階段混合檢索配置
  enable_hybrid_search?: boolean;
  enable_diversity_optimization?: boolean;
  search_type?: 'hybrid' | 'summary_only' | 'chunks_only' | 'legacy' | 'rrf_fusion';
  query_expansion_factor?: number;
  rerank_top_k?: number;
  
  // RRF 融合檢索權重配置
  rrf_weights?: Record<string, number>;
  rrf_k_constant?: number;
}

export interface SemanticSearchResult {
  document_id: string;
  similarity_score: number;
  summary_text: string;
  metadata?: Record<string, any>;
  
  // 新增：混合搜索相關字段
  vector_type?: 'summary' | 'chunk'; // 向量類型：摘要向量或文本塊向量
  chunk_index?: number; // 如果是文本塊，顯示是第幾個塊
  search_stage?: 'stage1' | 'stage2' | 'single'; // 搜索階段標識
  
  // 文檔基本信息
  document_filename?: string;
  document_status?: string;
  content_type?: string; // 文檔內容類型
  
  // 關鍵信息
  key_terms?: string[]; // 關鍵詞
  knowledge_domains?: string[]; // 知識領域
  searchable_keywords?: string[]; // 可搜索關鍵詞
  
  // 文本內容
  chunk_text?: string; // 如果是文本塊搜索，顯示具體的塊內容
  context_text?: string; // 上下文文本（用於預覽）
  
  // 搜索策略相關
  ranking_score?: number; // 重排序後的分數
  diversity_score?: number; // 多樣性分數
}

// AI QA Related (Legacy or specific QA parts)
export interface AIQARequest { // This is the older one, still used by askAIQuestion wrapper
  question: string;
  context_limit?: number;
  use_semantic_search?: boolean;
  use_structured_filter?: boolean;
  session_id?: string | null;
}

export interface QueryRewriteResult { // Used in AIQAResponse
  original_query: string;
  rewritten_queries: string[];
  extracted_parameters: Record<string, any>;
  intent_analysis?: string | null;
  
  // 新增：智能策略路由字段
  query_granularity?: string | null; // "thematic", "detailed", "unknown"
  search_strategy_suggestion?: string | null; // "summary_only", "rrf_fusion", "keyword_enhanced_rrf"
  reasoning?: string | null; // AI 對原始問題的分析推理過程
}

export interface LLMContextDocument {
  document_id: string;
  content_used: string;
  source_type: string;
}

export interface SemanticContextDocument {
  document_id: string;
  summary_or_chunk_text: string;
  similarity_score: number;
  metadata?: Record<string, any> | null;
}

export interface AIQAResponse { // Content for AIResponse<AIQAResponse>
  answer: string;
  source_documents: string[];
  confidence_score?: number | null;
  tokens_used: number;
  processing_time: number;
  query_rewrite_result?: QueryRewriteResult | null;
  semantic_search_contexts?: SemanticContextDocument[] | null;
  llm_context_documents?: LLMContextDocument[] | null;
  detailed_document_data_from_ai_query?: any[] | null; // 從 AI 生成的查詢中獲取的詳細數據（數組格式）
  detailed_query_reasoning?: string | null; // AI 為何以及如何生成詳細查詢的原因
  // 新增:工作流相關欄位
  classification?: any; // 問題分類結果
  workflow_state?: any; // 工作流狀態
  next_action?: string; // 下一步操作
  pending_approval?: string; // 等待批准的類型
  error_message?: string; // 錯誤信息
  session_id?: string | null;
  created_at: string;
}

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

// Vector Database Management
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

// Database Connection Status
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

// Embedding Model Management
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

// BackendLogEntry for getLogs in LogsPage - can be defined here or in a logService.ts
export interface BackendLogEntry {
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