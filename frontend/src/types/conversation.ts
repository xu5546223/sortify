/**
 * 對話相關的 TypeScript 類型定義
 */

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  tokens_used?: number;
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

