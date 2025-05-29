import { apiClient } from './apiClient';
import type { ConnectionInfo, TunnelStatus, ConnectedUser, BackendConnectedDevice } from '../types/apiTypes';

// --- ConnectionPage 相關 API 函數 ---
const getConnectionInfo = async (): Promise<ConnectionInfo> => {
  console.log('API: Fetching connection info...');
  try {
    const response = await apiClient.get<ConnectionInfo>('/system/connection-info');
    console.log('API: Connection info fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to fetch connection info:', error);
    throw error;
  }
};

const getTunnelStatus = async (): Promise<TunnelStatus> => {
  console.log('API: Fetching tunnel status...');
  try {
    const response = await apiClient.get<TunnelStatus>('/system/tunnel-status');
    console.log('API: Tunnel status fetched:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to fetch tunnel status:', error);
    throw error;
  }
};

const getConnectedUsersList = async (): Promise<ConnectedUser[]> => {
  console.log('API: Fetching connected users list...');
  try {
    const response = await apiClient.get<BackendConnectedDevice[]>('/auth/users/'); // 更新端點路徑
    console.log('API: Connected users list fetched (raw):', response.data);
    const mappedUsers: ConnectedUser[] = response.data.map(device => ({
      id: device.device_id,
      name: device.device_name || 'Unknown Device',
      device: device.device_type || device.user_agent || 'N/A',
      connectionTime: new Date(device.first_connected_at).toLocaleString(),
    }));
    console.log('API: Connected users list mapped:', mappedUsers);
    return mappedUsers;
  } catch (error) {
    console.error('API: Failed to fetch connected users list:', error);
    throw error;
  }
};

const refreshConnectionInfo = async (): Promise<ConnectionInfo> => {
  console.log('API: Refreshing connection info...');
  try {
    const response = await apiClient.post<ConnectionInfo>('/system/connection-info/refresh');
    console.log('API: Connection info refreshed:', response.data);
    return response.data;
  } catch (error) {
    console.error('API: Failed to refresh connection info:', error);
    throw error;
  }
};

const disconnectUser = async (userId: string): Promise<{ success: boolean }> => {
  console.log(`API: Disconnecting user ${userId}...`);
  try {
    // BackendConnectedDevice is the expected return for a successful post,
    // but we only care about success for this simple case.
    await apiClient.post<BackendConnectedDevice>(`/auth/users/${userId}/disconnect`);
    return { success: true };
  } catch (error: any) {
    console.error(`API: Failed to disconnect user ${userId}:`, error);
    throw error;
  }
};

export const ConnectionAPI = {
  getConnectionInfo,
  getTunnelStatus,
  getConnectedUsersList,
  refreshConnectionInfo,
  disconnectUser
}; 