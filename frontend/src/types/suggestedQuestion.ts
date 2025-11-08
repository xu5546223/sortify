/**
 * 建議問題相關的類型定義
 */

export enum QuestionType {
  SUMMARY = 'summary',
  COMPARISON = 'comparison',
  ANALYSIS = 'analysis',
  TIME_BASED = 'time_based',
  DETAIL_QUERY = 'detail_query',
  CROSS_CATEGORY = 'cross_category'
}

export interface SuggestedQuestion {
  id: string;
  question: string;
  category?: string;
  category_id?: string;
  related_documents: string[];
  is_cross_category: boolean;
  question_type: QuestionType;
  created_at: string;
  last_used_at?: string;
  use_count: number;
}

export interface GetSuggestedQuestionsResponse {
  questions: SuggestedQuestion[];
  total: number;
}

export interface GenerateQuestionsRequest {
  force_regenerate?: boolean;
  questions_per_category?: number;
  include_cross_category?: boolean;
}

export interface GenerateQuestionsResponse {
  success: boolean;
  message: string;
  task_id?: string;  // 後台任務ID
  total_questions?: number;
  questions?: SuggestedQuestion[];
}

