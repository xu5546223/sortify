/**
 * 手機端樣式測試頁面
 * 用於驗證 mobile.css 是否正確應用
 */

import React, { useEffect, useState } from 'react';
import MobileHeader from '../components/MobileHeader';

const MobileStyleTest: React.FC = () => {
  const [cssVars, setCssVars] = useState<Record<string, string>>({});
  const [bodyBg, setBodyBg] = useState('');

  useEffect(() => {
    // 檢查 CSS 變量
    const root = document.documentElement;
    const computedStyle = getComputedStyle(root);
    
    const vars = {
      'primary': computedStyle.getPropertyValue('--mobile-primary'),
      'primary-light': computedStyle.getPropertyValue('--mobile-primary-light'),
      'secondary': computedStyle.getPropertyValue('--mobile-secondary'),
      'danger': computedStyle.getPropertyValue('--mobile-danger'),
      'warning': computedStyle.getPropertyValue('--mobile-warning'),
      'bg': computedStyle.getPropertyValue('--mobile-bg'),
      'card-bg': computedStyle.getPropertyValue('--mobile-card-bg'),
      'text': computedStyle.getPropertyValue('--mobile-text'),
      'text-light': computedStyle.getPropertyValue('--mobile-text-light'),
      'border': computedStyle.getPropertyValue('--mobile-border')
    };
    
    setCssVars(vars);
    setBodyBg(getComputedStyle(document.body).backgroundColor);
  }, []);

  return (
    <>
      <MobileHeader title="樣式測試" showBack />
      
      <div style={{ padding: '16px', backgroundColor: 'var(--mobile-bg)', minHeight: 'calc(100vh - 56px - 60px)' }}>
        {/* Body 背景色檢查 */}
        <div className="mobile-card">
          <h3 className="mobile-card-title">Body 背景色</h3>
          <div style={{
            padding: '16px',
            backgroundColor: bodyBg,
            border: '2px solid var(--mobile-border)',
            borderRadius: '8px',
            textAlign: 'center'
          }}>
            <div style={{ fontSize: '14px', color: 'var(--mobile-text)', marginBottom: '8px' }}>
              當前背景色: <strong>{bodyBg}</strong>
            </div>
            <div style={{ fontSize: '13px', color: 'var(--mobile-text-light)' }}>
              預期: <strong>rgb(248, 249, 250)</strong> 或 <strong>#f8f9fa</strong>
            </div>
            <div style={{ 
              marginTop: '8px', 
              padding: '8px', 
              backgroundColor: bodyBg === 'rgb(248, 249, 250)' ? 'var(--mobile-primary)' : 'var(--mobile-danger)',
              color: 'white',
              borderRadius: '4px',
              fontWeight: '600'
            }}>
              {bodyBg === 'rgb(248, 249, 250)' ? '✅ 正確' : '❌ 錯誤'}
            </div>
          </div>
        </div>

        {/* CSS 變量檢查 */}
        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <h3 className="mobile-card-title">CSS 變量檢查</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {Object.entries(cssVars).map(([key, value]) => (
              <div 
                key={key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px',
                  backgroundColor: 'var(--mobile-bg)',
                  borderRadius: '8px',
                  border: '1px solid var(--mobile-border)'
                }}
              >
                <span style={{ fontSize: '14px', fontWeight: '500', color: 'var(--mobile-text)' }}>
                  --mobile-{key}
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {value && (
                    <div 
                      style={{
                        width: '32px',
                        height: '32px',
                        backgroundColor: value.trim(),
                        border: '2px solid var(--mobile-border)',
                        borderRadius: '4px'
                      }}
                    />
                  )}
                  <span style={{ 
                    fontSize: '12px', 
                    color: 'var(--mobile-text-light)',
                    fontFamily: 'monospace',
                    maxWidth: '120px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {value.trim() || '❌ 未定義'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 組件測試 */}
        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <h3 className="mobile-card-title">組件樣式測試</h3>
          
          {/* 按鈕測試 */}
          <div style={{ marginBottom: '16px' }}>
            <h4 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '8px', color: 'var(--mobile-text)' }}>
              按鈕樣式
            </h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button className="mobile-btn mobile-btn-primary">Primary Button</button>
              <button className="mobile-btn mobile-btn-secondary">Secondary Button</button>
              <button className="mobile-btn mobile-btn-warning">Warning Button</button>
              <button className="mobile-btn mobile-btn-danger">Danger Button</button>
              <button className="mobile-btn mobile-btn-outline">Outline Button</button>
            </div>
          </div>

          {/* 輸入框測試 */}
          <div style={{ marginBottom: '16px' }}>
            <h4 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '8px', color: 'var(--mobile-text)' }}>
              輸入框樣式
            </h4>
            <input 
              className="mobile-input" 
              placeholder="測試輸入框..." 
            />
          </div>

          {/* Badge 測試 */}
          <div style={{ marginBottom: '16px' }}>
            <h4 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '8px', color: 'var(--mobile-text)' }}>
              Badge 樣式
            </h4>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <span className="mobile-badge mobile-badge-primary">Primary</span>
              <span className="mobile-badge mobile-badge-success">Success</span>
              <span className="mobile-badge mobile-badge-warning">Warning</span>
              <span className="mobile-badge mobile-badge-danger">Danger</span>
            </div>
          </div>

          {/* 載入動畫測試 */}
          <div>
            <h4 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '8px', color: 'var(--mobile-text)' }}>
              載入動畫
            </h4>
            <div className="mobile-loading">
              <div className="mobile-loading-spinner" />
            </div>
          </div>
        </div>

        {/* 空狀態測試 */}
        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <div className="mobile-empty">
            <div className="mobile-empty-icon">📱</div>
            <div className="mobile-empty-text">空狀態範例</div>
            <div className="mobile-empty-subtext">這是副標題文字</div>
          </div>
        </div>

        {/* 診斷信息 */}
        <div className="mobile-card" style={{ marginTop: '16px', backgroundColor: '#fff9e6', border: '2px solid var(--mobile-warning)' }}>
          <h3 style={{ fontSize: '16px', fontWeight: '600', margin: '0 0 12px 0', color: 'var(--mobile-warning)' }}>
            🔍 診斷信息
          </h3>
          <div style={{ fontSize: '13px', color: 'var(--mobile-text)', lineHeight: '1.8' }}>
            <p><strong>User Agent:</strong> {navigator.userAgent}</p>
            <p><strong>Viewport Width:</strong> {window.innerWidth}px</p>
            <p><strong>Viewport Height:</strong> {window.innerHeight}px</p>
            <p><strong>Device Pixel Ratio:</strong> {window.devicePixelRatio}</p>
          </div>
        </div>
      </div>
    </>
  );
};

export default MobileStyleTest;

