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
}

export interface AIServiceSettingsUpdate {
  provider?: string;
  model?: string | null;
  temperature?: number | null;
  ensure_chinese_output?: boolean | null;
  max_output_tokens?: number | null;
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
  ensure_chinese_output?: boolean | null;
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
}

export interface SemanticSearchResult {
  document_id: string;
  similarity_score: number;
  summary_text: string;
  metadata?: Record<string, any>;
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