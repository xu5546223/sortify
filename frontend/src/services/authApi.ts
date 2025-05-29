import { apiClient } from './apiClient';

// --- 介面定義 (根據 frontend_data_types.md) ---

/**
 * Token 介面 (登入回應)
 * 對應後端 token_models.Token
 */
export interface Token {
  access_token: string;
  token_type: string;
}

/**
 * LoginRequest 介面 (登入請求)
 */
export interface LoginRequest {
  username: string;
  password: string;
}

/**
 * UserRegistrationRequest 介面 (使用者註冊請求)
 * 對應後端 user_models.UserCreate
 */
export interface UserRegistrationRequest {
  username: string;
  email?: string | null;
  full_name?: string | null;
  password: string;
  is_active?: boolean; // 後端預設為 true
}

/**
 * User 介面 (使用者資訊回應)
 * 對應後端 user_models.User
 */
export interface User {
  id: string; // UUID
  username: string;
  email?: string | null;
  full_name?: string | null;
  is_active: boolean;
  created_at: string; // ISO datetime string
  updated_at: string; // ISO datetime string
}

/**
 * UserUpdateRequest 介面 (更新使用者個人資料請求)
 * 對應後端 user_models.UserUpdate
 * 用於 PUT /api/v1/auth/users/me
 */
export interface UserUpdateRequest {
  email?: string | null;
  full_name?: string | null;
  // is_active?: boolean | null; // 根據文件，後端 API 會阻止用戶自行將 is_active 設為 false，通常不由用戶直接更新此欄位
}

/**
 * PasswordUpdateInRequest 介面 (更新使用者密碼請求)
 * 對應後端 user_models.PasswordUpdateIn
 * 用於 PUT /api/v1/auth/users/me/password
 */
export interface PasswordUpdateInRequest {
  current_password: string;
  new_password: string; // 後端模型要求 min_length=8
}

/**
 * API 錯誤回應介面
 */
export interface APIError {
  detail: string | Array<{
    loc: (string | number)[];
    msg: string;
    type: string;
  }>;
  error_code?: string;
  timestamp?: string;
}

/**
 * 標準化的API回應介面
 */
export interface AuthResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  details?: string;
}

// --- API 函數 ---

/**
 * 使用者登入
 * @param credentials 登入憑證
 * @returns Promise<Token> 包含 access_token 和 token_type
 */
export const loginUser = async (credentials: LoginRequest): Promise<Token> => {
  try {
    const formData = new URLSearchParams();
    formData.append('username', credentials.username);
    formData.append('password', credentials.password);

    const response = await apiClient.post<Token>('/auth/token', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    // 登入成功後，將 token 儲存到 localStorage
    if (response.data.access_token) {
      localStorage.setItem('authToken', response.data.access_token);
      console.log('Login successful, token stored');
    }
    return response.data;
  } catch (error: any) {
    console.error('Login failed:', error);
    
    // 處理不同類型的錯誤
    if (error.response) {
      const errorData = error.response.data as APIError;
      let errorMessage = '登入失敗';
      
      if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail.map(err => err.msg).join(', ');
      }
      
      throw new Error(errorMessage);
    }
    
    throw new Error('網路連接錯誤，請檢查您的網路設定');
  }
};

/**
 * 使用者註冊
 * @param userData 註冊資訊
 * @returns Promise<User> 註冊成功後的使用者資訊
 */
export const registerUser = async (userData: UserRegistrationRequest): Promise<User> => {
  try {
    const response = await apiClient.post<User>('/auth/register', userData);
    console.log('Registration successful:', response.data);
    return response.data;
  } catch (error: any) {
    console.error('Registration failed:', error);
    
    if (error.response) {
      const errorData = error.response.data as APIError;
      let errorMessage = '註冊失敗';
      
      if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail.map(err => err.msg).join(', ');
      }
      
      // 處理常見的註冊錯誤
      if (errorMessage.includes('username') || errorMessage.includes('用戶名')) {
        errorMessage = '用戶名已存在或格式不正確';
      } else if (errorMessage.includes('email') || errorMessage.includes('郵箱')) {
        errorMessage = '郵箱已存在或格式不正確';
      } else if (errorMessage.includes('password') || errorMessage.includes('密碼')) {
        errorMessage = '密碼格式不符合要求（至少8位字符）';
      }
      
      throw new Error(errorMessage);
    }
    
    throw new Error('網路連接錯誤，請檢查您的網路設定');
  }
};

/**
 * 獲取當前登入使用者的資訊
 * @returns Promise<User> 當前使用者資訊
 */
export const getCurrentUser = async (): Promise<User> => {
  try {
    const response = await apiClient.get<User>('/auth/users/me');
    console.log('Current user fetched:', response.data);
    return response.data;
  } catch (error: any) {
    console.error('Failed to fetch current user:', error);
    
    if (error.response?.status === 401) {
      // Token 過期或無效
      localStorage.removeItem('authToken');
      throw new Error('登入已過期，請重新登入');
    }
    
    throw new Error('無法獲取用戶資訊');
  }
};

/**
 * 更新當前登入使用者的資訊
 * @param userData 更新的使用者資料
 * @returns Promise<User> 更新後的使用者資訊
 */
export const updateCurrentUser = async (userData: UserUpdateRequest): Promise<User> => {
  try {
    const response = await apiClient.put<User>('/auth/users/me', userData);
    console.log('User updated successfully:', response.data);
    return response.data;
  } catch (error: any) {
    console.error('Failed to update current user:', error);
    
    if (error.response) {
      const errorData = error.response.data as APIError;
      let errorMessage = '更新用戶資訊失敗';
      
      if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail.map(err => err.msg).join(', ');
      }
      
      throw new Error(errorMessage);
    }
    
    throw new Error('網路連接錯誤，請檢查您的網路設定');
  }
};

/**
 * 更新當前登入使用者的密碼
 * @param passwordData 新舊密碼資訊
 * @returns Promise<{ message: string }> 成功訊息
 */
export const updatePassword = async (passwordData: PasswordUpdateInRequest): Promise<{ message: string }> => {
  try {
    const response = await apiClient.put<{ message: string }>('/auth/users/me/password', passwordData);
    console.log('Password updated successfully:', response.data);
    return response.data;
  } catch (error: any) {
    console.error('Failed to update password:', error);
    
    if (error.response) {
      const errorData = error.response.data as APIError;
      let errorMessage = '更新密碼失敗';
      
      if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail.map(err => err.msg).join(', ');
      }
      
      // 處理常見的密碼更新錯誤
      if (errorMessage.includes('current_password') || errorMessage.includes('當前密碼')) {
        errorMessage = '當前密碼錯誤';
      } else if (errorMessage.includes('new_password') || errorMessage.includes('新密碼')) {
        errorMessage = '新密碼格式不符合要求（至少8位字符）';
      }
      
      throw new Error(errorMessage);
    }
    
    throw new Error('網路連接錯誤，請檢查您的網路設定');
  }
};

/**
 * 使用者登出
 * 清除儲存的 token 和相關狀態
 */
export const logoutUser = (): void => {
  try {
    // 清除 localStorage 中的認證資訊
    localStorage.removeItem('authToken');
    
    // 可以在此處添加其他清理邏輯
    // 例如：清除用戶狀態、重置應用狀態等
    
    console.log('User logged out successfully');
  } catch (error) {
    console.error('Error during logout:', error);
  }
};

/**
 * 檢查用戶是否已登入
 * @returns boolean 是否已登入
 */
export const isUserLoggedIn = (): boolean => {
  const token = localStorage.getItem('authToken');
  
  if (!token) {
    return false;
  }
  
  try {
    // 檢查 JWT token 是否過期
    const payload = JSON.parse(atob(token.split('.')[1]));
    const currentTime = Date.now() / 1000;
    
    if (payload.exp && payload.exp < currentTime) {
      // Token 已過期，清除它
      localStorage.removeItem('authToken');
      return false;
    }
    
    return true;
  } catch (error) {
    // Token 格式無效，清除它
    console.warn('Invalid token format, removing token');
    localStorage.removeItem('authToken');
    return false;
  }
};

/**
 * 獲取當前儲存的認證 Token
 * @returns string | null 認證 Token 或 null
 */
export const getAuthToken = (): string | null => {
  return localStorage.getItem('authToken');
};

/**
 * 檢查 Token 是否即將過期
 * @param minutesThreshold 提前多少分鐘算作即將過期，預設5分鐘
 * @returns boolean 是否即將過期
 */
export const isTokenExpiringSoon = (minutesThreshold: number = 5): boolean => {
  const token = getAuthToken();
  
  if (!token) {
    return true;
  }
  
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    const expirationTime = payload.exp * 1000;
    const currentTime = Date.now();
    const threshold = minutesThreshold * 60 * 1000;
    
    return (expirationTime - currentTime) < threshold;
  } catch (error) {
    console.warn('Error checking token expiration:', error);
    return true;
  }
};

/**
 * 統一的認證 API 調用包裝器
 * @param operation 要執行的操作
 * @param errorMessage 自定義錯誤訊息
 * @returns Promise<T> 操作結果
 */
export const authApiCall = async <T>(
  operation: () => Promise<T>,
  errorMessage = '認證操作失敗'
): Promise<T> => {
  try {
    return await operation();
  } catch (error: any) {
    console.error(errorMessage, error);
    
    // 如果是認證錯誤，自動清除 token
    if (error.response?.status === 401) {
      localStorage.removeItem('authToken');
    }
    
    throw error;
  }
};

/**
 * 驗證當前 Token 的有效性
 * @returns Promise<boolean> Token 是否有效
 */
export const validateToken = async (): Promise<boolean> => {
  try {
    await getCurrentUser();
    return true;
  } catch (error) {
    return false;
  }
};

// 匯出認證相關的工具函數
export const AuthUtils = {
  isUserLoggedIn,
  getAuthToken,
  isTokenExpiringSoon,
  validateToken,
  authApiCall
};

// 匯出預設的認證API對象
export default {
  loginUser,
  registerUser,
  getCurrentUser,
  updateCurrentUser,
  updatePassword,
  logoutUser,
  ...AuthUtils
}; 