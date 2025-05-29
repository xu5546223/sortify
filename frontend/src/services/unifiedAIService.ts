import { apiClient } from './apiClient';
import type {
  AIRequest, // Base request type, might not be directly used if specific requests are comprehensive
  AIResponse,
  AITextAnalysisRequest,
  AITextAnalysisOutput,
  AIImageAnalysisRequest,
  AIQARequestUnified,
  AIQAResponse,
  QueryRewriteRequest,
  QueryRewriteResponse,
  AIModelInfo,
  AISystemStatus,
  TokenUsage // For AIResponse
} from '../types/apiTypes';
import axios from 'axios'; // For AxiosError type checking

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
    const response = await apiClient.post<AIResponse<AIQAResponse> | AIQAResponse>('/unified-ai/qa', request);
    console.log('API: AI問答原始響應:', response.data);

    if (response.data && 'answer' in response.data && 'tokens_used' in response.data) {
      const directResponse = response.data as AIQAResponse;
      return {
        success: true, 
        content: directResponse,
        model_used: (directResponse as any).model_used || undefined, 
        processing_time: directResponse.processing_time || undefined,
        token_usage: { 
          prompt_tokens: 0, 
          completion_tokens: directResponse.tokens_used || 0,
          total_tokens: directResponse.tokens_used || 0,
        },
        created_at: directResponse.created_at
      };
    } else if (response.data && 'content' in response.data && (response.data as AIResponse<AIQAResponse>).success !== undefined) {
      const responseObject = response.data as AIResponse<AIQAResponse>;
      console.log('API: AI問答完成 (包裹在 AIResponse 結構中):', { success: responseObject.success, model_used: responseObject.model_used });
      return responseObject;
    } else {
      console.error('API: AI問答返回了非預期的結構:', response.data);
      throw new Error('AI問答返回了非預期的響應結構');
    }
  } catch (error) {
    console.error('API: AI問答失敗(askAIQuestionUnified):', error);
    if (axios.isAxiosError(error) && error.response && error.response.data && (error.response.data as any).detail) {
      throw new Error((error.response.data as any).detail);
    }
    throw error;
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