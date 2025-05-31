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
  autoConnect: false,
  autoSync: false,
  // isDatabaseConnected is not part of SettingsData in api.ts, 
  // but getSettings might return it. We should handle its potential absence/presence.
  // For initial state, it can be omitted if not strictly part of SettingsData type.
  // Let's assume getSettings response structure is the source of truth for `settings` state.
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
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
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
  autoConnect?: boolean;
  autoSync?: boolean;
} 