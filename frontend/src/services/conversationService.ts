import { apiClient } from './apiClient';
import type {
  Conversation,
  ConversationWithMessages,
  ConversationCreateRequest,
  ConversationUpdateRequest,
  ConversationListResponse,
  ConversationMessage
} from '../types/conversation';

/**
 * 對話服務 - 處理所有對話相關的 API 調用
 */
export const conversationService = {
  /**
   * 創建新對話
   */
  createConversation: async (firstQuestion: string): Promise<Conversation> => {
    console.log('API: 創建新對話...', { firstQuestion: firstQuestion.substring(0, 50) });
    try {
      const request: ConversationCreateRequest = { first_question: firstQuestion };
      const response = await apiClient.post<Conversation>('/conversations', request);
      console.log('API: 對話創建成功:', { id: response.data.id });
      return response.data;
    } catch (error) {
      console.error('API: 創建對話失敗:', error);
      throw error;
    }
  },

  /**
   * 獲取用戶的對話列表
   */
  listConversations: async (skip: number = 0, limit: number = 50): Promise<ConversationListResponse> => {
    console.log('API: 獲取對話列表...', { skip, limit });
    try {
      const response = await apiClient.get<ConversationListResponse>('/conversations', {
        params: { skip, limit }
      });
      console.log('API: 對話列表獲取成功:', { 
        total: response.data.total, 
        count: response.data.conversations.length 
      });
      
      // 調試：檢查每個對話的 cached_documents
      response.data.conversations.forEach((conv, index) => {
        console.log(`  [${index}] ${conv.id}:`, {
          title: conv.title,
          cached_documents: conv.cached_documents,
          cached_docs_length: conv.cached_documents?.length || 0
        });
      });
      
      return response.data;
    } catch (error) {
      console.error('API: 獲取對話列表失敗:', error);
      throw error;
    }
  },

  /**
   * 獲取單個對話（包含所有消息）
   */
  getConversation: async (conversationId: string): Promise<ConversationWithMessages> => {
    console.log('API: 獲取對話詳情...', { conversationId });
    try {
      const response = await apiClient.get<ConversationWithMessages>(`/conversations/${conversationId}`);
      console.log('API: 對話詳情獲取成功:', { messageCount: response.data.messages.length });
      return response.data;
    } catch (error) {
      console.error('API: 獲取對話詳情失敗:', error);
      throw error;
    }
  },

  /**
   * 獲取對話的消息列表
   */
  getConversationMessages: async (conversationId: string, limit: number = 50): Promise<ConversationMessage[]> => {
    console.log('API: 獲取對話消息...', { conversationId, limit });
    try {
      const response = await apiClient.get<ConversationMessage[]>(`/conversations/${conversationId}/messages`, {
        params: { limit }
      });
      console.log('API: 對話消息獲取成功:', { count: response.data.length });
      return response.data;
    } catch (error) {
      console.error('API: 獲取對話消息失敗:', error);
      throw error;
    }
  },

  /**
   * 更新對話信息
   */
  updateConversation: async (conversationId: string, update: ConversationUpdateRequest): Promise<Conversation> => {
    console.log('API: 更新對話...', { conversationId, update });
    try {
      const response = await apiClient.put<Conversation>(`/conversations/${conversationId}`, update);
      console.log('API: 對話更新成功');
      return response.data;
    } catch (error) {
      console.error('API: 更新對話失敗:', error);
      throw error;
    }
  },

  /**
   * 刪除對話
   */
  deleteConversation: async (conversationId: string): Promise<void> => {
    console.log('API: 刪除對話...', { conversationId });
    try {
      await apiClient.delete(`/conversations/${conversationId}`);
      console.log('API: 對話刪除成功');
    } catch (error) {
      console.error('API: 刪除對話失敗:', error);
      throw error;
    }
  },

  /**
   * 從對話緩存中移除文檔
   */
  removeCachedDocument: async (conversationId: string, documentId: string): Promise<void> => {
    console.log('API: 移除緩存文檔...', { conversationId, documentId });
    try {
      await apiClient.delete(`/conversations/${conversationId}/cached-documents/${documentId}`);
      console.log('API: 緩存文檔移除成功');
    } catch (error) {
      console.error('API: 移除緩存文檔失敗:', error);
      throw error;
    }
  },

  /**
   * 僅分類問題(不執行後續流程)
   */
  classifyQuestion: async (question: string): Promise<any> => {
    console.log('API: 分類問題...', { question: question.substring(0, 50) });
    try {
      const response = await apiClient.post('/unified-ai/qa/classify', null, {
        params: { question }
      });
      console.log('API: 問題分類成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('API: 問題分類失敗:', error);
      throw error;
    }
  },

  /**
   * 獲取QA工作流配置
   */
  getQAConfig: async (): Promise<any> => {
    console.log('API: 獲取QA配置...');
    try {
      const response = await apiClient.get('/unified-ai/qa/config');
      console.log('API: QA配置獲取成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('API: 獲取QA配置失敗:', error);
      throw error;
    }
  },

  /**
   * 更新QA工作流配置
   */
  updateQAConfig: async (config: any): Promise<any> => {
    console.log('API: 更新QA配置...', { config });
    try {
      const response = await apiClient.put('/unified-ai/qa/config', config);
      console.log('API: QA配置更新成功');
      return response.data;
    } catch (error) {
      console.error('API: 更新QA配置失敗:', error);
      throw error;
    }
  },

  /**
   * 置頂對話
   */
  pinConversation: async (conversationId: string): Promise<Conversation> => {
    console.log('API: 置頂對話...', { conversationId });
    try {
      const response = await apiClient.post<Conversation>(`/conversations/${conversationId}/pin`);
      console.log('API: 對話置頂成功');
      return response.data;
    } catch (error) {
      console.error('API: 置頂對話失敗:', error);
      throw error;
    }
  },

  /**
   * 取消置頂對話
   */
  unpinConversation: async (conversationId: string): Promise<Conversation> => {
    console.log('API: 取消置頂對話...', { conversationId });
    try {
      const response = await apiClient.post<Conversation>(`/conversations/${conversationId}/unpin`);
      console.log('API: 對話取消置頂成功');
      return response.data;
    } catch (error) {
      console.error('API: 取消置頂對話失敗:', error);
      throw error;
    }
  }
};

export default conversationService;

