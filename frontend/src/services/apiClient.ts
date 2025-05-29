import axios from 'axios';

// 從環境變數讀取 API 基礎 URL，若無則使用預設值
const API_BASE_URL = process.env.REACT_APP_API_URL || '';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 更新的請求攔截器 - 支援新的認證要求
apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('authToken');
  
  // 定義需要認證的端點模式
  const authRequiredEndpoints = [
    '/vector-db/',
    '/embedding/',
    '/unified-ai/',
    '/documents/',
    '/dashboard/',
    '/logs/',
    '/auth/users/' // 用戶相關端點需要認證
  ];
  
  // 檢查當前請求是否需要認證
  const requiresAuth = authRequiredEndpoints.some(endpoint => 
    config.url?.includes(endpoint)
  );
  
  if (token) {
    // 確保 config.headers 存在，如果不存在則初始化
    if (!config.headers) {
      config.headers = {} as import('axios').AxiosRequestHeaders;
    }
    config.headers.Authorization = `Bearer ${token}`;
  } else if (requiresAuth) {
    // 如果需要認證但沒有token，記錄警告
    console.warn('API request requires authentication but no token found:', config.url);
  }

  // 如果請求的 data 是 FormData 實例，則刪除 Content-Type header，
  // 讓 axios 自動設置為 multipart/form-data 並包含正確的 boundary。
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  
  return config;
});

// 改進的回應攔截器 - 統一錯誤處理
apiClient.interceptors.response.use(
  response => response,
  error => {
    // 處理認證錯誤
    if (error.response?.status === 401) {
      console.warn('Authentication failed, removing token and redirecting to login');
      localStorage.removeItem('authToken');
      // 可以在此處添加重定向邏輯
      // window.location.href = '/login';
    }
    
    // 處理權限錯誤
    if (error.response?.status === 403) {
      console.error('Access denied:', error.response.data);
    }
    
    // 統一錯誤格式處理
    const errorMessage = error.response?.data?.detail || error.message || '請求發生錯誤';
    console.error('API Error:', {
      status: error.response?.status,
      message: errorMessage,
      url: error.config?.url
    });
    
    return Promise.reject(error);
  }
);

// 考慮將 apiCall 輔助函式也放在這裡，或者一個單獨的 apiUtils.ts
export const apiCall = async <T>(
  operation: () => Promise<T>,
  errorMessage = '操作失敗'
): Promise<T> => {
  try {
    return await operation();
  } catch (error) {
    console.error(errorMessage, error);
    throw error;
  }
}; 