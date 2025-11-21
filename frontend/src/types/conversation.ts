/**
 * 對話相關的 TypeScript 類型定義
 */

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  tokens_used?: number;
}

export interface DocumentPoolItem {
  document_id: string;
  filename: string;
  summary?: string;
  relevance_score?: number;
  access_count?: number;
  key_concepts?: string[];
  semantic_tags?: string[];
  first_mentioned_round?: number;
  last_accessed_round?: number;
}

export interface Conversation {
  id: string;
  title: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  total_tokens: number;
  cached_documents: string[];  // 緩存的文檔ID列表
  cached_document_data?: Record<string, DocumentPoolItem>;  // 文檔池（含摘要和元數據）
  is_pinned?: boolean;  // 是否置頂
}

export interface ConversationWithMessages extends Conversation {
  messages: ConversationMessage[];
}

export interface ConversationCreateRequest {
  first_question: string;
}

export interface ConversationUpdateRequest {
  title?: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

