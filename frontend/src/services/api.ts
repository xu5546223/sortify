import { askAIQuestionUnified } from './unifiedAIService';
import type { AIQARequestUnified, AIQAResponse, AIResponse } from '../types/apiTypes'; // Ensure types are available
// This file now re-exports from the new service modules and type definitions.
// Consider updating imports in your components to point directly to the new service files.

// Export API client instance (and apiCall utility if it was there)
export { apiClient, apiCall } from './apiClient';

// Export all types from apiTypes
export * from '../types/apiTypes';

// Export all services
export * from './connectionService';
export * from './dashboardService';
export * from './systemService';
export * from './documentService';
export * from './logService';
export * from './unifiedAIService';
export * from './vectorDBService';
export * from './embeddingService';

// Specific functions that were wrappers or might need decision:

// AI問答 (兼容性包裝 for askAIQuestionUnified)
// This function wraps the newer askAIQuestionUnified.
// If you are migrating, consider using askAIQuestionUnified directly.
// Ensure types are available

export const askAIQuestion = async (question: string, session_id?: string): Promise<AIQAResponse> => {
  console.log('API: 調用AI問答 (兼容性包裝)...', { question_length: question?.length });
  try {
    const request: AIQARequestUnified = {
      question,
      session_id,
      use_semantic_search: true,
      context_limit: 10,
      ensure_chinese_output: true // Default values from original api.ts
    };
    
    const response: AIResponse<AIQAResponse> = await askAIQuestionUnified(request);
    
    if ((response.success === undefined || response.success) && response.content) {
      return response.content;
    } else {
      // Log the full error response if available
      console.error('AI 問答 (兼容性包裝) 失敗:', response.error_message, response);
      throw new Error(response.error_message || 'AI問答 (兼容性包裝) 失敗，未收到預期內容。');
    }
  } catch (error) {
    console.error('API: AI問答 (兼容性包裝) 失敗:', error);
    // If the error is already an Error object, rethrow it, otherwise wrap it.
    if (error instanceof Error) {
        throw error;
    }
    throw new Error(String(error) || 'AI問答 (兼容性包裝) 發生未知錯誤');
  }
};

// Conversation History functions (getConversationHistory, clearConversationHistory)
// were originally using /unified-ai/conversation-history.
// Let's assume they are better placed in unifiedAIService.ts.
// If they were moved there, they are re-exported above.
// If they need to exist separately and were not part of the original unifiedAI functions list for that service,
// they would need to be defined here or in their own service file.

// For now, we assume they were moved to unifiedAIService.ts or are handled by its exports.

// Note: The TokenManager class has been moved to 'src/utils/tokenManager.ts'
// It should be imported from there directly where needed, e.g.:
// import { TokenManager } from '../utils/tokenManager';

console.log("New api.ts (re-exporter) created. Please update imports in your project to point to specific service files for better modularity."); 