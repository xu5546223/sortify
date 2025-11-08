/**
 * 裝置檢測 Hook
 * 用於檢測當前裝置類型並提供響應式功能
 */

import { useState, useEffect } from 'react';
import { isMobileDevice, isTabletDevice, isIOSDevice, isAndroidDevice, isInstalledPWA } from '../utils/pwaUtils';

interface DeviceInfo {
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  isIOS: boolean;
  isAndroid: boolean;
  isPWA: boolean;
  screenWidth: number;
  screenHeight: number;
  orientation: 'portrait' | 'landscape';
}

export const useMobileDetect = (): DeviceInfo => {
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo>(() => {
    const isMobile = isMobileDevice();
    const isTablet = isTabletDevice();
    
    return {
      isMobile,
      isTablet,
      isDesktop: !isMobile && !isTablet,
      isIOS: isIOSDevice(),
      isAndroid: isAndroidDevice(),
      isPWA: isInstalledPWA(),
      screenWidth: window.innerWidth,
      screenHeight: window.innerHeight,
      orientation: window.innerWidth > window.innerHeight ? 'landscape' : 'portrait'
    };
  });

  useEffect(() => {
    const updateDeviceInfo = () => {
      const isMobile = isMobileDevice();
      const isTablet = isTabletDevice();
      
      setDeviceInfo({
        isMobile,
        isTablet,
        isDesktop: !isMobile && !isTablet,
        isIOS: isIOSDevice(),
        isAndroid: isAndroidDevice(),
        isPWA: isInstalledPWA(),
        screenWidth: window.innerWidth,
        screenHeight: window.innerHeight,
        orientation: window.innerWidth > window.innerHeight ? 'landscape' : 'portrait'
      });
    };

    // 監聽視窗大小變化
    window.addEventListener('resize', updateDeviceInfo);
    
    // 監聽方向變化
    window.addEventListener('orientationchange', updateDeviceInfo);

    // 清理監聽器
    return () => {
      window.removeEventListener('resize', updateDeviceInfo);
      window.removeEventListener('orientationchange', updateDeviceInfo);
    };
  }, []);

  return deviceInfo;
};

/**
 * 簡化版的手機檢測 Hook
 */
export const useIsMobile = (): boolean => {
  const { isMobile } = useMobileDetect();
  return isMobile;
};

/**
 * 檢測是否為 PWA 的 Hook
 */
export const useIsPWA = (): boolean => {
  const { isPWA } = useMobileDetect();
  return isPWA;
};

