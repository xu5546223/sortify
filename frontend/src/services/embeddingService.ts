import { apiClient } from './apiClient';
import type {
  EmbeddingModelStatus,
  EmbeddingModelConfig,
  ModelLoadResult,
  ModelUnloadResult,
  DeviceConfigResult
} from '../types/apiTypes';

// 加載Embedding模型
export const loadEmbeddingModel = async (): Promise<ModelLoadResult> => {
  const response = await apiClient.post<ModelLoadResult>('/embedding/load');
  return response.data;
};

// 獲取Embedding模型配置
export const getEmbeddingModelConfig = async (): Promise<EmbeddingModelConfig> => {
  const response = await apiClient.get<EmbeddingModelConfig>('/embedding/config');
  return response.data;
};

// 配置Embedding模型設備
export const configureEmbeddingModel = async (devicePreference: 'cpu' | 'cuda' | 'auto'): Promise<DeviceConfigResult> => {
  const response = await apiClient.post<DeviceConfigResult>('/embedding/configure-device', {
    device_preference: devicePreference 
  });
  return response.data;
};

// 獲取Embedding模型狀態
export const getEmbeddingModelStatus = async (): Promise<EmbeddingModelStatus> => {
  const response = await apiClient.get<EmbeddingModelStatus>('/embedding/status');
  return response.data;
};

// 卸載Embedding模型
export const unloadEmbeddingModel = async (): Promise<ModelUnloadResult> => {
  const response = await apiClient.post<ModelUnloadResult>('/embedding/unload');
  return response.data;
}; 