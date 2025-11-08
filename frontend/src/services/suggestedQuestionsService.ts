/**
 * 建議問題 API 服務
 */

import { apiClient } from './apiClient';
import type {
  SuggestedQuestion,
  GetSuggestedQuestionsResponse,
  GenerateQuestionsRequest,
  GenerateQuestionsResponse
} from '../types/suggestedQuestion';

/**
 * 獲取建議問題（隨機不重複）
 * @param count 需要的問題數量（默認 4）
 */
export const getSuggestedQuestions = async (
  count: number = 4
): Promise<GetSuggestedQuestionsResponse> => {
  try {
    const response = await apiClient.get(`/suggested-questions`, {
      params: { count }
    });
    return response.data;
  } catch (error) {
    console.error('獲取建議問題失敗:', error);
    throw error;
  }
};

/**
 * 生成建議問題
 * @param request 生成請求參數
 */
export const generateSuggestedQuestions = async (
  request: GenerateQuestionsRequest = {}
): Promise<GenerateQuestionsResponse> => {
  try {
    const response = await apiClient.post(`/suggested-questions/generate`, request);
    return response.data;
  } catch (error) {
    console.error('生成建議問題失敗:', error);
    throw error;
  }
};

/**
 * 標記問題已使用
 * @param questionId 問題 ID
 */
export const markQuestionUsed = async (questionId: string): Promise<void> => {
  try {
    await apiClient.put(`/suggested-questions/${questionId}/use`);
  } catch (error) {
    console.error('標記問題使用失敗:', error);
    // 非關鍵操作，失敗不拋出錯誤
  }
};

/**
 * 獲取所有建議問題
 */
export const getAllSuggestedQuestions = async (): Promise<GetSuggestedQuestionsResponse> => {
  try {
    const response = await apiClient.get(`/suggested-questions/all`);
    return response.data;
  } catch (error) {
    console.error('獲取所有建議問題失敗:', error);
    throw error;
  }
};

/**
 * 刪除所有建議問題
 */
export const deleteAllSuggestedQuestions = async (): Promise<void> => {
  try {
    await apiClient.delete(`/suggested-questions`);
  } catch (error) {
    console.error('刪除建議問題失敗:', error);
    throw error;
  }
};

const suggestedQuestionsService = {
  getSuggestedQuestions,
  generateSuggestedQuestions,
  markQuestionUsed,
  getAllSuggestedQuestions,
  deleteAllSuggestedQuestions
};

export default suggestedQuestionsService;

