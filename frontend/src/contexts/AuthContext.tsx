import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as authApi from '../services/authApi';

interface AuthContextType {
  currentUser: authApi.User | null;
  token: string | null;
  isLoading: boolean;
  login: (credentials: authApi.LoginRequest) => Promise<void>;
  register: (userData: authApi.UserRegistrationRequest) => Promise<void>;
  logout: () => void;
  fetchCurrentUser: () => Promise<void>; // 新增函數以在應用程式載入時獲取使用者
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [currentUser, setCurrentUser] = useState<authApi.User | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('authToken'));
  const [isLoading, setIsLoading] = useState<boolean>(true); // 初始設為 true，直到首次使用者驗證完成

  useEffect(() => {
    const initialAuthCheck = async () => {
      const storedToken = localStorage.getItem('authToken');
      if (storedToken) {
        setToken(storedToken);
        // 不需要立即設定 apiClient.defaults.headers.common，因為攔截器會處理
        try {
          // console.log('AuthContext: Attempting to fetch current user with token');
          const user = await authApi.getCurrentUser();
          setCurrentUser(user);
          // console.log('AuthContext: Current user fetched', user);
        } catch (error) {
          console.error('AuthContext: Failed to fetch user with stored token', error);
          // Token 可能無效或過期，清除它
          localStorage.removeItem('authToken');
          setToken(null);
          setCurrentUser(null);
          // 清除 axios 的預設 header (如果之前有設定的話)
          // delete apiClient.defaults.headers.common['Authorization']; 
          // 攔截器會處理，所以這裡不需要
        }
      } else {
        // console.log('AuthContext: No stored token found');
      }
      setIsLoading(false);
    };

    initialAuthCheck();
  }, []); // 空依賴陣列，確保只在組件掛載時執行一次

  const login = async (credentials: authApi.LoginRequest) => {
    setIsLoading(true);
    try {
      const tokenData = await authApi.loginUser(credentials);
      setToken(tokenData.access_token);
      // localStorage.setItem('authToken', tokenData.access_token); // loginUser 內部已處理
      // console.log('AuthContext: Login successful, token set');
      await fetchCurrentUser(); // 登入後立即獲取使用者資訊
    } catch (error) {
      console.error('AuthContext: Login failed', error);
      setCurrentUser(null);
      setToken(null);
      setIsLoading(false);
      throw error; // 重新拋出錯誤，讓呼叫方處理 (例如顯示錯誤訊息)
    }
  };

  const register = async (userData: authApi.UserRegistrationRequest) => {
    setIsLoading(true);
    try {
      // 註冊後通常不會自動登入，或取決於後端設計。此處假設註冊後需手動登入。
      // 如果註冊後自動登入並回傳 token，則需要相應處理。
      await authApi.registerUser(userData);
      // console.log('AuthContext: Registration successful');
      // 註冊成功後，可以選擇引導使用者登入，或如果API回傳token則自動登入
      setIsLoading(false);
    } catch (error) {
      console.error('AuthContext: Registration failed', error);
      setIsLoading(false);
      throw error;
    }
  };

  const logout = () => {
    // console.log('AuthContext: Logging out');
    authApi.logoutUser(); // 清除 localStorage 中的 token
    setCurrentUser(null);
    setToken(null);
    // delete apiClient.defaults.headers.common['Authorization']; // 攔截器會處理
    setIsLoading(false); 
    // 可以在這裡加入重定向到登入頁面的邏輯，如果 AuthProvider 不是在路由層級之上的話
    // window.location.href = '/login'; // 簡單粗暴的重定向方式，建議使用 useNavigate
  };

  const fetchCurrentUser = async () => {
    setIsLoading(true);
    try {
      const user = await authApi.getCurrentUser();
      setCurrentUser(user);
      // console.log('AuthContext: fetchCurrentUser successful', user);
    } catch (error) {
      console.error('AuthContext: Failed to fetch current user during fetchCurrentUser', error);
      // 如果獲取失敗 (可能是 token 失效)，則登出使用者
      setCurrentUser(null);
      setToken(null);
      localStorage.removeItem('authToken');
    }
    setIsLoading(false);
  };

  return (
    <AuthContext.Provider value={{ currentUser, token, isLoading, login, register, logout, fetchCurrentUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}; 