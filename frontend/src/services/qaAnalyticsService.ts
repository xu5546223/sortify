/**
 * QA統計分析服務
 * 
 * 處理問答系統統計數據的API調用
 */
import { apiClient } from './apiClient';

export interface QAStatistics {
  total_questions: number;
  time_range: string;
  by_intent: Record<string, {
    count: number;
    avg_confidence: number;
    avg_api_calls: number;
    avg_time: number;
  }>;
  avg_api_calls: number;
  avg_response_time: number;
  success_rate: number;
  cost_metrics: {
    total_tokens: number;
    avg_tokens_per_question: number;
    cost_saved_percentage: number;
    baseline_comparison: {
      old_avg_api_calls: number;
      new_avg_api_calls: number;
      improvement: string;
    };
  };
}

export interface PerformanceTrends {
  daily_stats: Array<{
    date: string;
    questions: number;
    avg_api_calls: number;
    avg_time: number;
  }>;
  period: string;
  total_days: number;
}

/**
 * QA統計分析服務
 */
export const qaAnalyticsService = {
  /**
   * 獲取QA統計數據
   */
  getStatistics: async (
    timeRange: string = '24h',
    intentFilter?: string
  ): Promise<QAStatistics> => {
    console.log('API: 獲取QA統計數據...', { timeRange, intentFilter });
    
    try {
      const params: any = { time_range: timeRange };
      if (intentFilter) {
        params.intent_filter = intentFilter;
      }

      const response = await apiClient.get<QAStatistics>(
        '/qa/analytics/statistics',
        { params }
      );

      console.log('API: QA統計數據獲取成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('API: 獲取QA統計失敗:', error);
      throw error;
    }
  },

  /**
   * 獲取性能趨勢
   */
  getPerformanceTrends: async (days: number = 7): Promise<PerformanceTrends> => {
    console.log('API: 獲取性能趨勢...', { days });

    try {
      const response = await apiClient.get<PerformanceTrends>(
        '/qa/analytics/trends',
        { params: { days } }
      );

      console.log('API: 性能趨勢獲取成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('API: 獲取性能趨勢失敗:', error);
      throw error;
    }
  },

  /**
   * 獲取統計摘要
   */
  getSummary: async (): Promise<any> => {
    console.log('API: 獲取統計摘要...');

    try {
      const response = await apiClient.get('/qa/analytics/summary');
      console.log('API: 統計摘要獲取成功:', response.data);
      return response.data;
    } catch (error) {
      console.error('API: 獲取統計摘要失敗:', error);
      throw error;
    }
  }
};

export default qaAnalyticsService;

