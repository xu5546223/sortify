/* eslint-disable no-restricted-globals */

// Service Worker for Sortify AI Assistant PWA
// 版本號，自動生成基於構建時間（避免手動更新）
const BUILD_TIMESTAMP = '{{BUILD_TIMESTAMP}}'; // 構建時自動替換
const CACHE_VERSION = `sortify-v3-${BUILD_TIMESTAMP || Date.now()}`;
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DYNAMIC_CACHE = `${CACHE_VERSION}-dynamic`;
const API_CACHE = `${CACHE_VERSION}-api`;

console.log('[Service Worker] Version:', CACHE_VERSION);

// 需要預緩存的靜態資源
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/static/css/main.css',
  '/static/js/main.js',
  '/manifest.json',
  '/images/pdflogo.png',
  '/images/wordlogo.png',
  '/images/excellogo.png',
  '/images/picturelogo.png',
  '/images/txtlogo.png'
];

// 安裝 Service Worker
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing...');
  
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      console.log('[Service Worker] Caching static assets');
      // 不等待所有資源緩存完成，允許部分失敗
      return Promise.allSettled(
        STATIC_ASSETS.map(url => 
          cache.add(url).catch(err => 
            console.log(`[Service Worker] Failed to cache ${url}:`, err)
          )
        )
      );
    }).then(() => {
      // 立即激活新的 Service Worker
      return self.skipWaiting();
    })
  );
});

// 激活 Service Worker
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating...');
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter(cacheName => cacheName.startsWith('sortify-') && cacheName !== STATIC_CACHE && cacheName !== DYNAMIC_CACHE && cacheName !== API_CACHE)
          .map(cacheName => {
            console.log('[Service Worker] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          })
      );
    }).then(() => {
      // 立即控制所有客戶端
      return self.clients.claim();
    })
  );
});

// 攔截網絡請求
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // 跳過 Chrome 擴展請求
  if (url.protocol === 'chrome-extension:') {
    return;
  }

  // API 請求：Network First 策略
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(request, API_CACHE));
    return;
  }

  // JS 和 CSS：使用 Stale-While-Revalidate 策略（先用緩存，後台更新）
  if (request.destination === 'style' || request.destination === 'script') {
    event.respondWith(staleWhileRevalidateStrategy(request, STATIC_CACHE));
    return;
  }

  // 圖片和字體：Cache First 策略（這些變化較少）
  if (request.destination === 'image' || request.destination === 'font') {
    event.respondWith(cacheFirstStrategy(request, STATIC_CACHE));
    return;
  }

  // HTML 頁面：Network First 策略
  if (request.destination === 'document') {
    event.respondWith(networkFirstStrategy(request, DYNAMIC_CACHE));
    return;
  }

  // 其他請求：Network First 策略
  event.respondWith(networkFirstStrategy(request, DYNAMIC_CACHE));
});

// Cache First 策略
async function cacheFirstStrategy(request, cacheName) {
  try {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    const networkResponse = await fetch(request);
    if (networkResponse && networkResponse.status === 200) {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.error('[Service Worker] Cache First failed:', error);
    
    // 如果是離線狀態，返回離線頁面
    if (request.destination === 'document') {
      return caches.match('/offline.html');
    }
    
    throw error;
  }
}

// Network First 策略
async function networkFirstStrategy(request, cacheName) {
  try {
    const networkResponse = await fetch(request);
    
    // 只緩存成功的 GET 請求
    if (networkResponse && networkResponse.status === 200 && request.method === 'GET') {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[Service Worker] Network First failed, trying cache:', error);
    
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // 如果是離線狀態且是文檔請求，返回離線頁面
    if (request.destination === 'document') {
      return caches.match('/offline.html');
    }
    
    throw error;
  }
}

// Stale-While-Revalidate 策略：先返回緩存，同時在後台更新
async function staleWhileRevalidateStrategy(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);
  
  // 後台更新緩存
  const fetchPromise = fetch(request).then((networkResponse) => {
    if (networkResponse && networkResponse.status === 200) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  }).catch((error) => {
    console.log('[Service Worker] Background update failed:', error);
    return cachedResponse; // 返回緩存的版本
  });
  
  // 如果有緩存，立即返回；否則等待網絡請求
  return cachedResponse || fetchPromise;
}

// 監聽消息事件
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CLEAR_CACHE') {
    event.waitUntil(
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames.map(cacheName => caches.delete(cacheName))
        );
      })
    );
  }
});

// 背景同步 - 用於文件上傳失敗重試
self.addEventListener('sync', (event) => {
  if (event.tag === 'upload-documents') {
    event.waitUntil(syncUploadDocuments());
  }
});

async function syncUploadDocuments() {
  try {
    // 從 IndexedDB 獲取待上傳的文件
    // 這裡需要配合前端的 IndexedDB 存儲實現
    console.log('[Service Worker] Syncing upload documents...');
    
    // TODO: 實現實際的上傳邏輯
    
  } catch (error) {
    console.error('[Service Worker] Sync upload failed:', error);
  }
}

// 推送通知
self.addEventListener('push', (event) => {
  const options = {
    body: event.data ? event.data.text() : '您有新的通知',
    icon: '/images/icon-192x192.png',
    badge: '/images/icon-72x72.png',
    vibrate: [200, 100, 200],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'explore',
        title: '查看詳情'
      },
      {
        action: 'close',
        title: '關閉'
      }
    ]
  };

  event.waitUntil(
    self.registration.showNotification('Sortify AI', options)
  );
});

// 通知點擊事件
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'explore') {
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

console.log('[Service Worker] Loaded');

