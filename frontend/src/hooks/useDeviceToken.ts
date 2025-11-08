/**
 * Device Token 管理 Hook
 * 用於管理手機端的長效認證 Token
 */

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../services/apiClient';
import { generateDeviceFingerprint, getDeviceName } from '../utils/pwaUtils';

interface DeviceTokenInfo {
  deviceToken: string;
  refreshToken: string;
  deviceId: string;
  expiresAt: string;
}

interface UseDeviceTokenReturn {
  hasDeviceToken: boolean;
  deviceToken: string | null;
  isRefreshing: boolean;
  pairDevice: (pairingToken: string) => Promise<boolean>;
  refreshDeviceToken: () => Promise<boolean>;
  clearDeviceToken: (resetDevice?: boolean) => void;
  getAccessToken: () => Promise<string | null>;
  getDeviceInfo: () => { deviceId: string | null; deviceUUID: string | null };
}

const DEVICE_TOKEN_KEY = 'sortify_device_token';
const REFRESH_TOKEN_KEY = 'sortify_refresh_token';
const DEVICE_ID_KEY = 'sortify_device_id';
const TOKEN_EXPIRES_KEY = 'sortify_token_expires';

export const useDeviceToken = (): UseDeviceTokenReturn => {
  const [hasDeviceToken, setHasDeviceToken] = useState<boolean>(false);
  const [deviceToken, setDeviceToken] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  // 初始化：檢查是否有儲存的 Device Token
  useEffect(() => {
    const savedDeviceToken = localStorage.getItem(DEVICE_TOKEN_KEY);
    const savedExpiresAt = localStorage.getItem(TOKEN_EXPIRES_KEY);

    console.log('🔍 初始化檢查 Device Token:', {
      hasDeviceToken: !!savedDeviceToken,
      expiresAt: savedExpiresAt
    });

    if (savedDeviceToken && savedExpiresAt) {
      const expiresAt = new Date(savedExpiresAt);
      const now = new Date();

      // 檢查是否過期
      if (expiresAt > now) {
        setDeviceToken(savedDeviceToken);
        setHasDeviceToken(true);
        // 確保 authToken 也被設置,讓 API 請求可以使用
        if (!localStorage.getItem('authToken')) {
          localStorage.setItem('authToken', savedDeviceToken);
          console.log('✅ 已恢復 Device Token 到 authToken');
        }
      } else {
        // Token 過期，清除
        console.warn('⚠️ Device Token 已過期,清除中...');
        clearDeviceToken();
      }
    }
  }, []);

  /**
   * 配對新裝置
   */
  const pairDevice = useCallback(async (pairingToken: string): Promise<boolean> => {
    try {
      const deviceFingerprint = generateDeviceFingerprint();
      const deviceName = getDeviceName();

      const response = await apiClient.post<{
        device_token: string;
        refresh_token: string;
        device_id: string;
        expires_at: string;
      }>('/device-auth/pair-device', {
        pairing_token: pairingToken,
        device_name: deviceName,
        device_fingerprint: deviceFingerprint
      });

      // 儲存 Token
      localStorage.setItem(DEVICE_TOKEN_KEY, response.data.device_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, response.data.refresh_token);
      localStorage.setItem(DEVICE_ID_KEY, response.data.device_id);
      localStorage.setItem(TOKEN_EXPIRES_KEY, response.data.expires_at);
      // 同時設置 authToken,讓 API 請求可以使用
      localStorage.setItem('authToken', response.data.device_token);

      setDeviceToken(response.data.device_token);
      setHasDeviceToken(true);
      
      // 觸發自定義事件,通知其他組件配對狀態已變更
      window.dispatchEvent(new Event('pairing-status-changed'));
      
      console.log('✅ 配對成功,Token 已儲存:', {
        hasDeviceToken: true,
        deviceId: response.data.device_id,
        expiresAt: response.data.expires_at
      });

      return true;
    } catch (error) {
      console.error('配對裝置失敗:', error);
      return false;
    }
  }, []);

  /**
   * 刷新 Device Token
   */
  const refreshDeviceToken = useCallback(async (): Promise<boolean> => {
    if (isRefreshing) {
      console.log('🔄 正在刷新中,跳過重複請求');
      return false;
    }

    setIsRefreshing(true);

    try {
      const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
      const deviceId = localStorage.getItem(DEVICE_ID_KEY);

      console.log('🔄 開始刷新 Device Token:', {
        hasRefreshToken: !!refreshToken,
        hasDeviceId: !!deviceId
      });

      if (!refreshToken || !deviceId) {
        console.error('❌ 沒有 Refresh Token 或 Device ID');
        clearDeviceToken();
        return false;
      }

      const response = await apiClient.post<{
        access_token: string;
        token_type: string;
      }>('/device-auth/refresh', {
        refresh_token: refreshToken,
        device_id: deviceId
      });

      // 更新 Access Token (同時更新到兩個地方)
      const newAccessToken = response.data.access_token;
      localStorage.setItem('authToken', newAccessToken);
      localStorage.setItem(DEVICE_TOKEN_KEY, newAccessToken);
      
      setDeviceToken(newAccessToken);
      
      console.log('✅ Token 刷新成功');

      return true;
    } catch (error) {
      console.error('❌ 刷新 Token 失敗:', error);
      
      // 如果刷新失敗，清除所有 Token
      clearDeviceToken();
      
      return false;
    } finally {
      setIsRefreshing(false);
    }
  }, [isRefreshing]);

  /**
   * 清除 Device Token
   * @param resetDevice 是否同時重置設備 UUID（重置後視為新設備，需要重新授權）
   */
  const clearDeviceToken = useCallback((resetDevice: boolean = false) => {
    console.log('🗑️ 清除 Device Token', { resetDevice });
    
    localStorage.removeItem(DEVICE_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(DEVICE_ID_KEY);
    localStorage.removeItem(TOKEN_EXPIRES_KEY);
    localStorage.removeItem('authToken');

    // 如果需要重置設備，同時清除設備 UUID
    if (resetDevice) {
      localStorage.removeItem('sortify_device_uuid');
      console.log('🔄 已重置設備 UUID，下次配對將視為新設備');
    }

    setDeviceToken(null);
    setHasDeviceToken(false);
    
    // 觸發自定義事件,通知其他組件配對狀態已變更
    window.dispatchEvent(new Event('pairing-status-changed'));
  }, []);

  /**
   * 獲取有效的 Access Token
   * 如果 Token 即將過期，自動刷新
   */
  const getAccessToken = useCallback(async (): Promise<string | null> => {
    const authToken = localStorage.getItem('authToken');
    
    if (!authToken) {
      // 嘗試刷新 Token
      const refreshed = await refreshDeviceToken();
      if (refreshed) {
        return localStorage.getItem('authToken');
      }
      return null;
    }

    // TODO: 檢查 Token 是否即將過期（可選）
    // 如果即將過期，提前刷新

    return authToken;
  }, [refreshDeviceToken]);

  /**
   * 獲取設備信息
   */
  const getDeviceInfo = useCallback(() => {
    const deviceId = localStorage.getItem(DEVICE_ID_KEY);
    const deviceUUID = localStorage.getItem('sortify_device_uuid');
    
    return {
      deviceId,
      deviceUUID
    };
  }, []);

  return {
    hasDeviceToken,
    deviceToken,
    isRefreshing,
    pairDevice,
    refreshDeviceToken,
    clearDeviceToken,
    getAccessToken,
    getDeviceInfo
  };
};

