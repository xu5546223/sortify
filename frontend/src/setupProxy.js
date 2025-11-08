/**
 * Create React App 代理配置
 * 只代理 API 請求，不影響 HMR
 */

const { createProxyMiddleware } = require('http-proxy-middleware');

// 啟動時的日誌
console.log('');
console.log('========================================');
console.log('🔧 setupProxy.js 已載入！');
console.log('📡 代理配置: /api/* → http://localhost:8000/api/*');
console.log('========================================');
console.log('');

module.exports = function(app) {
  // 只代理以 /api/ 開頭的請求到後端
  // ⚠️ 重要：在 v3+ 中，使用 app.use('/api', ...) 時，
  //           target 也必須包含 '/api' 路徑
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8000/api',  // 包含 /api 前綴
      changeOrigin: true,
      // 不需要 pathRewrite，因為已經在 target 中處理
      onProxyReq: (proxyReq, req, res) => {
        // 調試日誌：顯示完整的代理路徑
        console.log('🔄 代理請求:', req.method, req.originalUrl, '→', proxyReq.path);
      },
      onError: (err, req, res) => {
        console.error('❌ 代理錯誤:', err.message);
      }
    })
  );

  // 添加 Cache-Control headers 來禁用快取（開發環境）
  app.use((req, res, next) => {
    // 只對非 API 請求添加 no-cache headers
    if (!req.path.startsWith('/api')) {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
      res.setHeader('Pragma', 'no-cache');
      res.setHeader('Expires', '0');
    }
    next();
  });
};

