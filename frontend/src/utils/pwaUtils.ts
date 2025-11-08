/**
 * PWA 工具函數
 * 用於裝置檢測、安裝提示、更新提示等
 */

/**
 * 檢測是否為手機裝置（包括平板）
 * 注意：iPad 在 iPadOS 13+ 可能會顯示為 Mac 的 User-Agent
 */
export const isMobileDevice = (): boolean => {
  // 檢測 User-Agent
  const userAgent = navigator.userAgent || navigator.vendor || (window as any).opera;
  const platform = navigator.platform || '';
  
  // 1. 檢測常見的移動裝置（包括 iPad）
  const mobileRegex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;
  if (mobileRegex.test(userAgent)) {
    return true;
  }
  
  // 2. 特殊檢測：iPad（iPadOS 13+ 會偽裝成 Mac）
  // 檢查是否有觸控支持、是平板尺寸、且平台是 Mac
  const hasTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const isMacPlatform = /Mac|MacIntel|MacPPC|Mac68K/i.test(platform);
  const isTabletSize = window.innerWidth >= 768 && window.innerWidth <= 1366;
  
  // 如果是 Mac 平台但有觸控支持，很可能是 iPad
  if (isMacPlatform && hasTouch && navigator.maxTouchPoints > 1) {
    console.log('🔍 檢測到可能是 iPad（偽裝成 Mac）');
    return true;
  }
  
  // 3. 檢測觸控支援和窄螢幕（手機）
  const isNarrowScreen = window.innerWidth <= 768;
  if (hasTouch && isNarrowScreen) {
    return true;
  }
  
  // 4. 檢測觸控支援和平板尺寸屏幕
  if (hasTouch && isTabletSize) {
    console.log('🔍 檢測到平板尺寸的觸控設備');
    return true;
  }
  
  return false;
};

/**
 * 檢測是否為平板裝置
 * 注意：iPad 在 iPadOS 13+ 可能會顯示為 Mac 的 User-Agent
 */
export const isTabletDevice = (): boolean => {
  const userAgent = navigator.userAgent || navigator.vendor || (window as any).opera;
  const platform = navigator.platform || '';
  const tabletRegex = /iPad|Android(?!.*Mobile)/i;
  
  // 1. 檢查 User-Agent 中明確的平板標識
  if (tabletRegex.test(userAgent)) {
    return true;
  }
  
  // 2. 特殊檢測：iPad（iPadOS 13+ 會偽裝成 Mac）
  const hasTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const isMacPlatform = /Mac|MacIntel|MacPPC|Mac68K/i.test(platform);
  
  // Mac 平台 + 多點觸控 = 很可能是 iPad
  if (isMacPlatform && hasTouch && navigator.maxTouchPoints > 1) {
    console.log('🔍 檢測到 iPad（偽裝成 Mac）');
    return true;
  }
  
  // 3. 檢測大尺寸觸控螢幕（768px - 1366px）
  const isTabletScreen = window.innerWidth > 768 && window.innerWidth <= 1366;
  
  return hasTouch && isTabletScreen;
};

/**
 * 檢測是否為 iOS 裝置
 * 注意：iPad 在 iPadOS 13+ 可能會顯示為 Mac 的 User-Agent
 */
export const isIOSDevice = (): boolean => {
  const userAgent = navigator.userAgent || navigator.vendor;
  const platform = navigator.platform || '';
  
  // 1. 檢查 User-Agent 中明確的 iOS 標識
  if (/iPhone|iPad|iPod/i.test(userAgent)) {
    return true;
  }
  
  // 2. 特殊檢測：iPad（iPadOS 13+ 會偽裝成 Mac）
  // Mac 平台 + 多點觸控 = 很可能是 iPad
  const hasTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const isMacPlatform = /Mac|MacIntel|MacPPC|Mac68K/i.test(platform);
  
  if (isMacPlatform && hasTouch && navigator.maxTouchPoints > 1) {
    return true;
  }
  
  return false;
};

/**
 * 檢測是否為 Android 裝置
 */
export const isAndroidDevice = (): boolean => {
  const userAgent = navigator.userAgent || navigator.vendor;
  return /Android/i.test(userAgent);
};

/**
 * 檢測是否已安裝為 PWA
 */
export const isInstalledPWA = (): boolean => {
  // 檢測 display-mode
  if (window.matchMedia('(display-mode: standalone)').matches) {
    return true;
  }
  
  // iOS Safari 的檢測
  if ((navigator as any).standalone === true) {
    return true;
  }
  
  return false;
};

/**
 * 檢測是否支援 PWA 安裝
 */
export const canInstallPWA = (): boolean => {
  // 檢測是否支援 beforeinstallprompt 事件
  return 'onbeforeinstallprompt' in window;
};

/**
 * PWA 安裝提示管理
 */
class PWAInstallManager {
  private deferredPrompt: any = null;
  private installCallback: ((canInstall: boolean) => void) | null = null;

  constructor() {
    this.initializeListeners();
  }

  private initializeListeners() {
    // 監聽 beforeinstallprompt 事件
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      this.deferredPrompt = e;
      
      if (this.installCallback) {
        this.installCallback(true);
      }
    });

    // 監聽 appinstalled 事件
    window.addEventListener('appinstalled', () => {
      console.log('PWA 已成功安裝');
      this.deferredPrompt = null;
      
      if (this.installCallback) {
        this.installCallback(false);
      }
    });
  }

  /**
   * 註冊安裝狀態變化回調
   */
  onInstallStateChange(callback: (canInstall: boolean) => void) {
    this.installCallback = callback;
    
    // 立即通知當前狀態
    callback(this.deferredPrompt !== null);
  }

  /**
   * 顯示安裝提示
   */
  async showInstallPrompt(): Promise<boolean> {
    if (!this.deferredPrompt) {
      console.warn('沒有可用的安裝提示');
      return false;
    }

    try {
      this.deferredPrompt.prompt();
      const { outcome } = await this.deferredPrompt.userChoice;
      
      console.log(`用戶選擇: ${outcome}`);
      
      if (outcome === 'accepted') {
        this.deferredPrompt = null;
        return true;
      }
      
      return false;
    } catch (error) {
      console.error('顯示安裝提示失敗:', error);
      return false;
    }
  }

  /**
   * 檢查是否可以顯示安裝提示
   */
  canShowInstallPrompt(): boolean {
    return this.deferredPrompt !== null;
  }
}

// 單例實例
export const pwaInstallManager = new PWAInstallManager();

/**
 * Service Worker 註冊
 */
export const registerServiceWorker = async (): Promise<ServiceWorkerRegistration | null> => {
  if ('serviceWorker' in navigator) {
    try {
      const registration = await navigator.serviceWorker.register('/service-worker.js', {
        scope: '/'
      });

      console.log('✅ Service Worker 註冊成功:', registration.scope);

      // 定期檢查更新（每 60 秒）
      setInterval(() => {
        registration.update().catch(err => 
          console.log('檢查更新失敗:', err)
        );
      }, 60000);

      // 檢查更新
      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        if (newWorker) {
          console.log('🔄 發現新版本 Service Worker');
          
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              // 有新版本可用
              console.log('✨ 新版本已準備就緒');
              
              // 觸發自定義事件，讓 App 組件顯示更新提示
              window.dispatchEvent(new CustomEvent('sw-update-available', {
                detail: { registration, newWorker }
              }));
              
              // 自動更新（不打擾用戶）
              console.log('🚀 自動應用新版本...');
              newWorker.postMessage({ type: 'SKIP_WAITING' });
              
              // 延遲 1 秒後重新載入（讓用戶有時間看到當前操作完成）
              setTimeout(() => {
                console.log('🔄 重新載入應用...');
                window.location.reload();
              }, 1000);
            }
          });
        }
      });

      // 監聽 Service Worker 控制器變化
      let refreshing = false;
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (!refreshing) {
          refreshing = true;
          console.log('🔄 Service Worker 控制器已更新');
          // 頁面會自動重新載入
        }
      });

      return registration;
    } catch (error) {
      console.error('❌ Service Worker 註冊失敗:', error);
      return null;
    }
  }

  console.warn('⚠️ 瀏覽器不支援 Service Worker');
  return null;
};

/**
 * 取消註冊 Service Worker
 */
export const unregisterServiceWorker = async (): Promise<boolean> => {
  if ('serviceWorker' in navigator) {
    try {
      const registration = await navigator.serviceWorker.ready;
      const success = await registration.unregister();
      console.log('Service Worker 取消註冊:', success);
      return success;
    } catch (error) {
      console.error('取消註冊 Service Worker 失敗:', error);
      return false;
    }
  }
  return false;
};

/**
 * 清除所有緩存
 */
export const clearAllCaches = async (): Promise<void> => {
  if ('caches' in window) {
    try {
      const cacheNames = await caches.keys();
      console.log('🗑️ 正在清除緩存:', cacheNames);
      await Promise.all(cacheNames.map(name => caches.delete(name)));
      console.log('✅ 所有緩存已清除');
    } catch (error) {
      console.error('❌ 清除緩存失敗:', error);
      throw error;
    }
  } else {
    console.warn('⚠️ 瀏覽器不支援 Cache API');
  }
};

/**
 * 強制更新應用（清除緩存 + 取消註冊 SW + 重新載入）
 */
export const forceUpdateApp = async (): Promise<void> => {
  console.log('🔄 開始強制更新應用...');
  
  try {
    // 1. 清除所有緩存
    await clearAllCaches();
    
    // 2. 取消註冊所有 Service Worker
    if ('serviceWorker' in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map(reg => reg.unregister()));
      console.log('✅ Service Worker 已取消註冊');
    }
    
    // 3. 清除 localStorage（可選，保留用戶數據）
    // localStorage.clear();
    
    console.log('✅ 強制更新完成，即將重新載入...');
    
    // 4. 重新載入頁面（繞過緩存）
    window.location.reload();
  } catch (error) {
    console.error('❌ 強制更新失敗:', error);
    throw error;
  }
};

/**
 * 獲取當前緩存信息（用於調試）
 */
export const getCacheInfo = async (): Promise<{
  cacheNames: string[];
  totalSize: number;
  cacheDetails: Array<{ name: string; urls: string[] }>;
}> => {
  if (!('caches' in window)) {
    return { cacheNames: [], totalSize: 0, cacheDetails: [] };
  }
  
  try {
    const cacheNames = await caches.keys();
    const cacheDetails = await Promise.all(
      cacheNames.map(async (name) => {
        const cache = await caches.open(name);
        const keys = await cache.keys();
        return {
          name,
          urls: keys.map(req => req.url)
        };
      })
    );
    
    const totalSize = cacheDetails.reduce((sum, cache) => sum + cache.urls.length, 0);
    
    return { cacheNames, totalSize, cacheDetails };
  } catch (error) {
    console.error('❌ 獲取緩存信息失敗:', error);
    return { cacheNames: [], totalSize: 0, cacheDetails: [] };
  }
};

/**
 * 生成或獲取持久化的裝置 UUID
 */
const getOrCreateDeviceUUID = (): string => {
  const DEVICE_UUID_KEY = 'sortify_device_uuid';
  
  // 嘗試從 localStorage 獲取
  let deviceUUID = localStorage.getItem(DEVICE_UUID_KEY);
  
  if (!deviceUUID) {
    // 生成新的 UUID
    deviceUUID = crypto.randomUUID();
    localStorage.setItem(DEVICE_UUID_KEY, deviceUUID);
    console.log('🆕 生成新的裝置 UUID:', deviceUUID);
  } else {
    console.log('✅ 使用現有的裝置 UUID:', deviceUUID);
  }
  
  return deviceUUID;
};

/**
 * 生成裝置指紋
 * 結合持久化 UUID 和設備特徵，確保同一設備有一致的指紋
 */
export const generateDeviceFingerprint = (): string => {
  const components: string[] = [];
  
  // 1. 持久化的裝置 UUID（最重要的標識）
  const deviceUUID = getOrCreateDeviceUUID();
  components.push(deviceUUID);
  
  // 2. User-Agent
  components.push(navigator.userAgent);
  
  // 3. 螢幕解析度
  components.push(`${window.screen.width}x${window.screen.height}x${window.screen.colorDepth}`);
  
  // 4. 平台
  components.push(navigator.platform);
  
  // 5. 語言
  components.push(navigator.language);
  
  // 6. 時區
  components.push(String(new Date().getTimezoneOffset()));
  
  // 7. 硬體並發數（CPU 核心數）
  components.push(String(navigator.hardwareConcurrency || 'unknown'));
  
  // 8. 裝置記憶體（如果可用）
  if ('deviceMemory' in navigator) {
    components.push(String((navigator as any).deviceMemory));
  }
  
  // 創建指紋字符串
  const fingerprintString = components.join('|');
  
  // 使用更強的 hash 函數
  return betterHash(fingerprintString);
};

/**
 * 改進的 hash 函數（使用 FNV-1a 算法）
 */
function betterHash(str: string): string {
  let hash = 2166136261; // FNV offset basis
  
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
  }
  
  // 轉換為十六進制並確保長度
  const hexHash = (hash >>> 0).toString(16);
  
  // 生成第二個 hash 來增加長度和唯一性
  let hash2 = 2166136261;
  for (let i = str.length - 1; i >= 0; i--) {
    hash2 ^= str.charCodeAt(i);
    hash2 += (hash2 << 1) + (hash2 << 4) + (hash2 << 7) + (hash2 << 8) + (hash2 << 24);
  }
  const hexHash2 = (hash2 >>> 0).toString(16);
  
  // 組合兩個 hash 並填充到 64 位
  const combined = (hexHash + hexHash2).padEnd(64, '0').substring(0, 64);
  return combined;
}

/**
 * 獲取裝置名稱（改進版）
 */
export const getDeviceName = (): string => {
  const userAgent = navigator.userAgent;
  const platform = navigator.platform;
  
  // iOS 裝置 - 嘗試識別具體型號
  if (/iPhone/.test(userAgent)) {
    // 嘗試從 User-Agent 提取 iPhone 型號
    const modelMatch = userAgent.match(/iPhone(\d+[,_]\d+)/);
    if (modelMatch) {
      return `iPhone (${modelMatch[1].replace(/[,_]/g, '.')})`;
    }
    return 'iPhone';
  }
  
  if (/iPad/.test(userAgent)) {
    const modelMatch = userAgent.match(/iPad(\d+[,_]\d+)/);
    if (modelMatch) {
      return `iPad (${modelMatch[1].replace(/[,_]/g, '.')})`;
    }
    return 'iPad';
  }
  
  if (/iPod/.test(userAgent)) {
    return 'iPod Touch';
  }
  
  // Android 裝置 - 改進型號提取
  if (/Android/.test(userAgent)) {
    // 提取 Android 版本
    const versionMatch = userAgent.match(/Android\s+([\d.]+)/);
    const version = versionMatch ? versionMatch[1] : '';
    
    // 嘗試提取裝置型號（多種模式）
    let model = '';
    
    // Pattern 1: Build/... 之前的內容
    const buildMatch = userAgent.match(/;\s*([^;]+)\s+Build\//);
    if (buildMatch && buildMatch[1]) {
      model = buildMatch[1].trim();
    }
    
    // Pattern 2: Android 版本後的內容
    if (!model) {
      const afterAndroid = userAgent.match(/Android[^;]+;\s*([^)]+)\)/);
      if (afterAndroid && afterAndroid[1]) {
        model = afterAndroid[1].trim();
      }
    }
    
    // 清理型號名稱（移除常見的前綴）
    if (model) {
      model = model
        .replace(/^(SM-|SAMSUNG-|SAMSUNG\s+)/i, '') // Samsung 前綴
        .replace(/^(MI\s+)/i, '') // Xiaomi 前綴
        .replace(/^(HUAWEI\s+)/i, '') // Huawei 前綴
        .replace(/^(OPPO\s+)/i, '') // OPPO 前綴
        .replace(/^(vivo\s+)/i, '') // vivo 前綴
        .replace(/^(OnePlus\s+)/i, '') // OnePlus 前綴
        .trim();
      
      // 如果型號有效且不是 "unknown"
      if (model && model.toLowerCase() !== 'unknown' && model.length < 40) {
        return version ? `${model} (Android ${version})` : model;
      }
    }
    
    // 嘗試識別品牌
    const brandMatch = userAgent.match(/(Samsung|Xiaomi|Huawei|OPPO|vivo|OnePlus|Google|Sony|LG|Motorola|Nokia|Asus|HTC)/i);
    if (brandMatch) {
      return version ? `${brandMatch[1]} Android ${version}` : `${brandMatch[1]} Android`;
    }
    
    return version ? `Android ${version}` : 'Android Device';
  }
  
  // 其他移動裝置
  if (/Windows Phone/.test(userAgent)) {
    return 'Windows Phone';
  }
  
  if (/BlackBerry/.test(userAgent)) {
    return 'BlackBerry';
  }
  
  // 桌面裝置
  if (/Mac/.test(platform) || /Macintosh/.test(userAgent)) {
    // 嘗試識別 macOS 版本
    const osMatch = userAgent.match(/Mac OS X ([\d_]+)/);
    if (osMatch) {
      const version = osMatch[1].replace(/_/g, '.');
      return `Mac (macOS ${version})`;
    }
    return 'Mac';
  }
  
  if (/Win/.test(platform) || /Windows/.test(userAgent)) {
    // 嘗試識別 Windows 版本
    if (/Windows NT 10/.test(userAgent)) {
      return 'Windows 10/11';
    }
    if (/Windows NT 6.3/.test(userAgent)) {
      return 'Windows 8.1';
    }
    if (/Windows NT 6.2/.test(userAgent)) {
      return 'Windows 8';
    }
    if (/Windows NT 6.1/.test(userAgent)) {
      return 'Windows 7';
    }
    return 'Windows PC';
  }
  
  if (/Linux/.test(platform) || /Linux/.test(userAgent)) {
    // 檢查是否是 Chrome OS
    if (/CrOS/.test(userAgent)) {
      return 'Chromebook';
    }
    return 'Linux PC';
  }
  
  // 瀏覽器檢測（作為最後的備選）
  if (/Chrome/.test(userAgent) && !/Edge/.test(userAgent)) {
    return 'Chrome Browser';
  }
  if (/Safari/.test(userAgent) && !/Chrome/.test(userAgent)) {
    return 'Safari Browser';
  }
  if (/Firefox/.test(userAgent)) {
    return 'Firefox Browser';
  }
  if (/Edge/.test(userAgent)) {
    return 'Edge Browser';
  }
  
  return 'Unknown Device';
};

/**
 * 請求通知權限
 */
export const requestNotificationPermission = async (): Promise<NotificationPermission> => {
  if (!('Notification' in window)) {
    console.warn('瀏覽器不支援通知');
    return 'denied';
  }

  if (Notification.permission === 'granted') {
    return 'granted';
  }

  if (Notification.permission !== 'denied') {
    const permission = await Notification.requestPermission();
    return permission;
  }

  return Notification.permission;
};

/**
 * 顯示本地通知
 */
export const showNotification = async (
  title: string,
  options?: NotificationOptions
): Promise<void> => {
  const permission = await requestNotificationPermission();
  
  if (permission === 'granted') {
    if ('serviceWorker' in navigator) {
      const registration = await navigator.serviceWorker.ready;
      await registration.showNotification(title, {
        icon: '/images/icon-192x192.png',
        badge: '/images/icon-72x72.png',
        ...options
      });
    } else {
      new Notification(title, {
        icon: '/images/icon-192x192.png',
        ...options
      });
    }
  }
};

