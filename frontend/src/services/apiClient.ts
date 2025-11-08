import axios from 'axios';

// 從環境變數讀取 API 基礎 URL，若無則使用相對路徑（透過 proxy）
// 使用相對路徑可以讓手機端通過同一個 tunnel 訪問後端
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || process.env.REACT_APP_API_URL || '/api/v1';

// 調試日誌
console.log('🔧 API Client 配置:');
console.log('  - REACT_APP_API_BASE_URL:', process.env.REACT_APP_API_BASE_URL);
console.log('  - REACT_APP_API_URL:', process.env.REACT_APP_API_URL);
console.log('  - 最終 API_BASE_URL:', API_BASE_URL);

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  paramsSerializer: {
    // 使用传统的数组参数序列化方式，FastAPI 期望的格式
    // 例如: ?status_in=value1&status_in=value2
    indexes: null, // 不使用索引格式 (不要 status_in[0]=value1)
  },
});

// 更新的請求攔截器 - 支援新的認證要求
apiClient.interceptors.request.use(config => {
  // 調試日誌：記錄完整的請求 URL
  const fullUrl = `${config.baseURL}${config.url}`;
  console.log('📡 API 請求:', config.method?.toUpperCase(), fullUrl);
  
  // 每次請求時都從 localStorage 讀取最新的 token，而不是使用快取的值
  // 支援電腦端的 authToken 和手機端的 device_token
  const authToken = localStorage.getItem('authToken');
  const deviceToken = localStorage.getItem('sortify_device_token');
  const token = authToken || deviceToken;
  
  // 定義需要認證的端點模式
  const authRequiredEndpoints = [
    '/vector-db/',
    '/embedding/',
    '/unified-ai/',
    '/documents/',
    '/dashboard/',
    '/logs/',
    '/gmail/',
    '/clustering/', // 聚類端點需要認證
    '/auth/users/', // 用戶相關端點需要認證
    '/qa/analytics/', // QA統計端點需要認證
    '/device-auth/devices', // 設備管理需要認證
    '/device-auth/cleanup' // 清理需要認證
  ];
  
  // 不需要強制認證的端點（即使有 token 也不警告）
  const optionalAuthEndpoints = [
    '/system/settings' // 系統設置可以不需要認證（使用默認值）
  ];
  
  // 檢查當前請求是否需要認證
  const requiresAuth = authRequiredEndpoints.some(endpoint => 
    config.url?.includes(endpoint)
  );
  
  // 檢查是否為可選認證端點
  const isOptionalAuth = optionalAuthEndpoints.some(endpoint =>
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
    console.warn('⚠️ API 請求需要認證但未找到 token:', config.url);
  } else if (isOptionalAuth) {
    // 可選認證端點，不警告
    console.log('ℹ️ 可選認證端點，將使用默認值:', config.url);
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
    // 處理認證錯誤 - 區分認證失敗和功能未授權
    if (error.response?.status === 401) {
      const detail = error.response?.data?.detail || '';
      
      // 🚨 檢查是否為設備被撤銷的錯誤
      const isDeviceRevoked = typeof detail === 'string' && 
        (detail.includes('設備授權已被撤銷') || 
         detail.includes('Device token') ||
         detail.includes('重新配對'));
      
      if (isDeviceRevoked) {
        console.error('🚫 設備授權已被撤銷！');
        
        // 清除所有設備相關的 token
        localStorage.removeItem('sortify_device_token');
        localStorage.removeItem('sortify_refresh_token');
        localStorage.removeItem('sortify_device_id');
        localStorage.removeItem('sortify_token_expires');
        localStorage.removeItem('authToken');
        
        // 觸發配對狀態變更事件
        window.dispatchEvent(new Event('pairing-status-changed'));
        
        // 如果是手機端，自動導航到配對頁面
        if (window.location.pathname.startsWith('/mobile')) {
          console.log('📱 導航到配對頁面');
          window.location.href = '/mobile/scan';
        }
        
        return Promise.reject(error);
      }
      
      const isFeatureAuthError = typeof detail === 'string' && 
        (detail.includes('Gmail') || 
         detail.includes('Google') || 
         detail.includes('授權') ||
         detail.includes('authorization'));
      
      if (!isFeatureAuthError) {
        // 這是真正的認證失敗 - 清除 token 並重定向
        console.warn('⚠️ 認證失敗，清除 token');
        
        // 檢查是否已經在重定向過程中（防止無限循環）
        const isRedirecting = sessionStorage.getItem('auth_redirecting');
        
        if (!isRedirecting) {
          // 標記正在重定向
          sessionStorage.setItem('auth_redirecting', 'true');
          
          localStorage.removeItem('authToken');
          localStorage.removeItem('sortify_device_token');
          
          // 觸發配對狀態變更事件
          window.dispatchEvent(new Event('pairing-status-changed'));
          
          // 延遲重定向，避免立即重載
          setTimeout(() => {
            sessionStorage.removeItem('auth_redirecting');
            
            // 根據當前路徑決定重定向
            if (window.location.pathname.startsWith('/mobile')) {
              // 避免從 scan 頁面重定向到 scan 頁面
              if (window.location.pathname !== '/mobile/scan') {
                window.location.href = '/mobile/scan';
              }
            } else if (!window.location.pathname.startsWith('/auth')) {
              // 電腦端重定向到登錄頁
              // window.location.href = '/auth/login';
            }
          }, 100);
        }
      } else {
        // 這是功能未授權 (如 Gmail 未授權) - 保留 token，讓組件處理
        console.warn('⚠️ 功能未授權:', detail);
      }
    }
    
    // 處理權限錯誤
    if (error.response?.status === 403) {
      console.error('❌ 訪問被拒絕:', error.response.data);
    }
    
    // 統一錯誤格式處理
    const errorMessage = error.response?.data?.detail || error.message || '請求發生錯誤';
    console.error('❌ API 錯誤:', {
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