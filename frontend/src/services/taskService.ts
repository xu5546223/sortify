/**
 * 後台任務服務
 */

import { apiClient } from './apiClient';

export interface TaskStatus {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  current_step: string;
  total_items: number;
  completed_items: number;
  result?: {
    total_questions: number;
    questions: any[];
  };
  error_message?: string;
}

export interface TaskPollingOptions {
  onProgress?: (status: TaskStatus) => void;
  onComplete?: (status: TaskStatus) => void;
  onError?: (error: string) => void;
  interval?: number;  // 輪詢間隔（毫秒）
  maxAttempts?: number;  // 最大輪詢次數
}

const taskService = {
  /**
   * 查詢任務狀態
   */
  getTaskStatus: async (taskId: string): Promise<TaskStatus> => {
    const response = await apiClient.get<TaskStatus>(`/suggested-questions/task/${taskId}`);
    return response.data;
  },

  /**
   * 輪詢任務狀態直到完成
   */
  pollTaskStatus: async (
    taskId: string,
    options: TaskPollingOptions = {}
  ): Promise<TaskStatus> => {
    const {
      onProgress,
      onComplete,
      onError,
      interval = 1000,  // 默認 1 秒輪詢一次
      maxAttempts = 300  // 默認最多輪詢 5 分鐘
    } = options;

    let attempts = 0;

    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          attempts++;

          if (attempts > maxAttempts) {
            const error = '任務超時';
            onError?.(error);
            reject(new Error(error));
            return;
          }

          const status = await taskService.getTaskStatus(taskId);

          // 調用進度回調
          onProgress?.(status);

          // 檢查任務狀態
          if (status.status === 'completed') {
            onComplete?.(status);
            resolve(status);
            return;
          }

          if (status.status === 'failed') {
            const error = status.error_message || '任務失敗';
            onError?.(error);
            reject(new Error(error));
            return;
          }

          // 繼續輪詢
          setTimeout(poll, interval);

        } catch (error: any) {
          const errorMsg = error?.response?.data?.detail || '查詢任務狀態失敗';
          onError?.(errorMsg);
          reject(error);
        }
      };

      // 開始輪詢
      poll();
    });
  }
};

export default taskService;

