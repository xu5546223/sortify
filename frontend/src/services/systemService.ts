import { apiClient } from './apiClient';
import type {
  SettingsData,
  UpdatableSettingsPayload,
  TestDBConnectionRequest,
  TestDBConnectionResponse,
  // TestApiKeyRequest, // Removed as per previous step
  // TestApiKeyResponse // Removed as per previous step
} from '../types/apiTypes';
import axios from 'axios'; // Import axios for isAxiosError check

export const getSettings = async (): Promise<SettingsData> => {
  console.log('API: Fetching settings...');
  try {
    const response = await apiClient.get<SettingsData>('/system/settings');
    console.log('API: Settings fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to fetch settings:', error);
    throw error;
  }
};

export const updateSettings = async (newSettings: UpdatableSettingsPayload): Promise<SettingsData> => {
  console.log('API: Updating settings...', newSettings);
  try {
    const response = await apiClient.put<SettingsData>('/system/settings', newSettings);
    console.log('API: Settings updated:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to update settings:', error);
    throw error;
  }
};

export const testDBConnection = async (payload: TestDBConnectionRequest): Promise<TestDBConnectionResponse> => {
  console.log('API: Testing DB connection...', payload);
  try {
    const response = await apiClient.post<TestDBConnectionResponse>('/system/test-db-connection', payload);
    console.log('API: DB connection test response:', response.data);
    return response.data;
  } catch (error: any) {
    console.error('API: Failed to test DB connection:', error.response?.data || error.message);
    if (error.response?.data && typeof error.response.data.success === 'boolean' && typeof error.response.data.message === 'string') {
      return error.response.data as TestDBConnectionResponse;
    }
    const errorMessage = error.response?.data?.detail || 
                         (error.response?.data?.message && typeof error.response?.data?.success === 'boolean' ? error.response.data.message : null) || 
                         (axios.isAxiosError(error) && error.message) || 
                         "測試資料庫連線時發生未知網路錯誤";
    const errorDetails = typeof error.response?.data?.detail === 'string' ? error.response.data.detail : undefined;

    return {
      success: false,
      message: errorMessage,
      error_details: errorDetails || (axios.isAxiosError(error) ? error.message : String(error)),
    };
  }
};

export const getGoogleAIModels = async (): Promise<string[]> => {
  console.log('API: Fetching Google AI models...');
  try {
    const response = await apiClient.get<string[]>('/system/ai-models/google');
    console.log('API: Google AI models fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to fetch Google AI models:', error);
    throw error;
  }
};

// export const testGoogleApiKey = async (apiKey: string): Promise<TestApiKeyResponse> => {
//   console.log(`API: Testing Google AI API Key ending with ...${apiKey.slice(-4)}`);
//   try {
//     const payload: TestApiKeyRequest = { api_key: apiKey };
//     const response = await apiClient.post<TestApiKeyResponse>('/system/test-ai-api-key', payload);
//     console.log('API: API Key test response:', response.data);
//     return response.data;
//   } catch (error: any) {
//     console.error('API: Failed to test API Key:', error);
//     if (axios.isAxiosError(error) && error.response) {
//       if (error.response.data && typeof error.response.data.is_valid === 'boolean') {
//         return error.response.data as TestApiKeyResponse;
//       }
//       return {
//         status: "error",
//         message: error.response.data?.detail || error.message || "測試 API 金鑰時發生未知網路或伺服器錯誤",
//         is_valid: false
//       };
//     }
//     return {
//       status: "error",
//       message: error.message || "測試 API 金鑰時發生未知錯誤",
//       is_valid: false
//     };
//   }
// }; 