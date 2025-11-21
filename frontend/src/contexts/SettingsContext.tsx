import React, { createContext, useState, useEffect, ReactNode, useCallback } from 'react';
import type {
  SettingsData,
  AIServiceSettings,
  DatabaseSettings,
  AIServiceSettingsUpdate,
  UpdatableSettingsPayload
} from '../types/apiTypes';
import {
  getSettings as apiGetSettings,
  updateSettings as apiUpdateSettings
} from '../services/systemService';

// Define the shape of the AI settings as part of the context
// This should align with what SettingsPage uses and what api.ts expects
// Note: field names are snake_case as updated previously
const defaultAiSettings: AIServiceSettings = {
  provider: 'google',
  model: '', // Default to empty, fetched from API
  temperature: 0.7,
  is_api_key_configured: false,
  ensure_chinese_output: true,
  max_output_tokens: null,
};

const defaultDbSettings: DatabaseSettings = {
  uri: '',
  dbName: '',
  // Removed trigger_content_processing, ai_force_stable_model, ai_ensure_chinese_output from defaultDbSettings
  // as they don't belong here based on api.ts DatabaseSettings definition.
  // They are part of DocumentUpdateRequest or specific trigger options.
};

// Define the initial state for the entire system settings
const initialSettings: SettingsData = {
  aiService: defaultAiSettings,
  database: defaultDbSettings,
};

export interface SettingsContextType {
  settings: SettingsData;
  isLoading: boolean;
  error: string | null;
  updateSettings: (newSettings: Partial<UpdatableSettingsPayload>) => Promise<void>; // Use UpdatableSettingsPayload
  refreshSettings: () => Promise<void>;
}

// Create the context with a default value
export const SettingsContext = createContext<SettingsContextType>({
  settings: initialSettings, // initialSettings is now SettingsData
  isLoading: true,
  error: null,
  updateSettings: async () => { console.warn('updateSettings called on default SettingsContext'); },
  refreshSettings: async () => { console.warn('refreshSettings called on default SettingsContext'); },
});

interface SettingsProviderProps {
  children: ReactNode;
}

export const SettingsProvider: React.FC<SettingsProviderProps> = ({ children }) => {
  const [settings, setSettings] = useState<SettingsData>(initialSettings);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    // 🔒 檢查是否在手機端且未配對
    const isMobile = window.location.pathname.startsWith('/mobile');
    const hasDeviceToken = localStorage.getItem('sortify_device_token');
    const hasAuthToken = localStorage.getItem('authToken');
    
    // 如果是手機端且沒有 token，使用默認設置而不請求 API
    if (isMobile && !hasDeviceToken && !hasAuthToken) {
      console.log('SettingsContext: 手機端未配對，使用默認設置');
      setSettings(initialSettings);
      setIsLoading(false);
      return;
    }
    
    console.log('SettingsContext: Fetching settings...');
    setIsLoading(true);
    setError(null);
    try {
      const fetchedSettings = await apiGetSettings(); // Returns SettingsData
      // Ensure the state structure matches SettingsData, merging carefully
      setSettings(prev => ({ // prev is SettingsData
        ...initialSettings, // Start with a well-defined base structure
        ...fetchedSettings, // Override with all fields from fetchedSettings
        // Explicitly merge aiService and database if they might be partial or need defaults
        aiService: {
          ...defaultAiSettings, // Base defaults for AI service
          ...(fetchedSettings.aiService || {}), // Merge what was fetched
        },
        database: {
          ...defaultDbSettings, // Base defaults for DB service
          ...(fetchedSettings.database || {}), // Merge what was fetched
        },
      }));
      console.log('SettingsContext: Settings fetched successfully:', fetchedSettings);
    } catch (err: any) {
      console.error('SettingsContext: Failed to fetch settings', err);
      setError(err.message || 'Failed to load settings');
      
      // 🔒 如果是 401 錯誤且在手機端，使用默認設置（避免無限循環）
      if (isMobile && err.response?.status === 401) {
        console.log('SettingsContext: 401 錯誤，使用默認設置');
        setSettings(initialSettings);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  // 🔄 監聽認證狀態變化，當用戶登錄/登出時自動重新載入設定
  useEffect(() => {
    const handleAuthChange = () => {
      console.log('SettingsContext: 檢測到認證狀態變化，重新載入設定');
      fetchSettings();
    };

    // 監聽自定義的認證狀態變化事件
    window.addEventListener('pairing-status-changed', handleAuthChange);
    window.addEventListener('auth-status-changed', handleAuthChange);

    return () => {
      window.removeEventListener('pairing-status-changed', handleAuthChange);
      window.removeEventListener('auth-status-changed', handleAuthChange);
    };
  }, [fetchSettings]);

  const updateSettingsHandler = async (newSettingsUpdate: Partial<UpdatableSettingsPayload>) => {
    console.log('SettingsContext: Attempting to update settings with:', newSettingsUpdate);
    setIsLoading(true);
    setError(null);
    try {
      const updatedSettingsData = await apiUpdateSettings(newSettingsUpdate); // Returns SettingsData
      // Merge updated settings into the current state
      setSettings(prev => ({ // prev is SettingsData
        ...prev, // Keep existing state for fields not in updatedSettingsData
        ...updatedSettingsData, // Override with new data
        // Explicitly merge aiService and database
        aiService: {
          ...(prev.aiService || defaultAiSettings), // Start with current or default
          ...(updatedSettingsData.aiService || {}), // Merge updates
        },
        database: {
          ...(prev.database || defaultDbSettings), // Start with current or default
          ...(updatedSettingsData.database || {}), // Merge updates
        },
      }));
      console.log('SettingsContext: Settings updated successfully:', updatedSettingsData);
    } catch (err: any) {
      console.error('SettingsContext: Failed to update settings', err);
      setError(err.message || 'Failed to update settings');
      throw err; // Re-throw to allow calling component to handle
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <SettingsContext.Provider 
      value={{ 
        settings, 
        isLoading, 
        error, 
        updateSettings: updateSettingsHandler, 
        refreshSettings: fetchSettings 
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
};

// SystemSettingsUpdate interface is removed as UpdatableSettingsPayload is used directly from api.ts

// Helper type for the update function argument, aligning with api.ts
// This might be slightly different from SystemSettings if e.g. apiKey is part of update but not get
export interface SystemSettingsUpdate {
  aiService?: AIServiceSettingsUpdate; // Use AIServiceSettingsUpdate for apiKey
  database?: Partial<DatabaseSettings>;
} 