import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { apiClient } from '../services/apiClient';
import { useAuth } from '../contexts/AuthContext';
import './GmailImporter.css';

interface GmailMessage {
  email_id: string;
  subject: string;
  from_address: string;
  snippet: string;
  date: string;
  size: number;
  is_unread: boolean;
  is_starred: boolean;
}

interface GmailImporterProps {
  visible: boolean;
  onClose: () => void;
  onSuccess?: (count: number) => void;
}

const GmailImporter: React.FC<GmailImporterProps> = ({ visible, onClose, onSuccess }) => {
  const [messages, setMessages] = useState<GmailMessage[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [query, setQuery] = useState('');
  const [tags, setTags] = useState<string>('');
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [authorizing, setAuthorizing] = useState(false);
  const [limit, setLimit] = useState(25);  // 新增：讀取郵件數量，預設 25 封

  const { token } = useAuth();
  
  // 🔥 使用 useRef 存儲清理函數
  const messageHandlerRef = useRef<((event: MessageEvent) => void) | null>(null);
  const timeoutIdRef = useRef<NodeJS.Timeout | null>(null);

  // 🔥 先定義 fetchMessages，因為 checkAuthorization 需要用它
  const showToast = (msg: string, type: 'success' | 'error' | 'warning' = 'success') => {
    // Simple toast notification (you can enhance this or use a toast library)
    const toast = document.createElement('div');
    toast.className = `toast-notification fixed top-4 right-4 px-6 py-3 border-3 border-neo-black font-bold uppercase z-[9999] ${
      type === 'success' ? 'bg-neo-primary' : type === 'error' ? 'bg-neo-error text-white' : 'bg-neo-warn'
    }`;
    toast.style.boxShadow = '4px 4px 0px 0px #000000';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(() => document.body.removeChild(toast), 300);
    }, 3000);
  };

  const fetchMessages = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiClient.get('/gmail/messages', {
        params: {
          query: query || '',
          limit: limit  // 使用自訂的 limit
        }
      });
      setMessages(response.data.messages || []);
    } catch (error: any) {
      if (error.response?.status === 401) {
        // Token 過期或未授權
        const detail = error.response?.data?.detail || '';
        if (detail.includes('過期') || detail.includes('撤銷')) {
          showToast('Gmail 授權已過期，請重新授權', 'warning');
        } else {
          showToast('Gmail 未授權，請先完成授權', 'warning');
        }
        setIsAuthorized(false);
        setMessages([]); // 清空郵件列表
      } else {
        showToast('無法獲取郵件列表: ' + (error.response?.data?.detail || error.message), 'error');
      }
    } finally {
      setLoading(false);
    }
  }, [query, limit]); // 依賴 query 和 limit

  // 🔥 使用 useCallback 包裝，避免無限循環
  const checkAuthorization = useCallback(async () => {
    try {
      setLoading(true);
      setAuthorizing(false); // 🔥 確保 authorizing 為 false
      
      // 使用輕量級端點檢查授權狀態，而不是獲取郵件列表
      const response = await apiClient.get('/gmail/check-auth-status');
      const { is_authorized } = response.data;
      
      if (is_authorized) {
        setIsAuthorized(true);
        // 授權後自動加載郵件列表（fetchMessages 會自己管理 loading 狀態）
        setLoading(false); // 🔥 先重置 loading
        await fetchMessages();
      } else {
        setIsAuthorized(false);
        setMessages([]);
        setLoading(false);
      }
    } catch (error: any) {
      console.error('檢查授權狀態失敗:', error);
      setIsAuthorized(false);
      setMessages([]);
      setLoading(false); // 🔥 確保 loading 被重置
      setAuthorizing(false); // 🔥 確保 authorizing 被重置
      // 不顯示錯誤提示，因為這只是狀態檢查
    }
  }, [fetchMessages]); // 依賴 fetchMessages

  // 獲取授權 URL 並重定向
  const handleAuthorize = async () => {
    try {
      setAuthorizing(true);
      const response = await apiClient.get('/gmail/authorize-url');
      const { auth_url } = response.data;
      
      // 在新窗口中打開授權 URL
      const popup = window.open(auth_url, 'Gmail Authorization', 'width=500,height=600');
      
      if (!popup) {
        showToast('無法打開授權窗口。請檢查浏覽器彈出窗口設定', 'error');
        setAuthorizing(false);
        return;
      }
      
      // 🔥 清理之前的監聽器
      if (messageHandlerRef.current) {
        window.removeEventListener('message', messageHandlerRef.current);
      }
      if (timeoutIdRef.current) {
        clearTimeout(timeoutIdRef.current);
      }

      // 使用 message 事件監聽授權完成
      const handleMessage = async (event: MessageEvent) => {
        // 驗證消息來源
        if (event.origin !== window.location.origin) return;
        
        if (event.data?.type === 'gmail_auth_complete' && event.data?.code) {
          // 🔥 清理
          if (messageHandlerRef.current) {
            window.removeEventListener('message', messageHandlerRef.current);
            messageHandlerRef.current = null;
          }
          if (timeoutIdRef.current) {
            clearTimeout(timeoutIdRef.current);
            timeoutIdRef.current = null;
          }
          
          try {
            // 向後端發送 authorization code 進行交換
            // 改為使用 Query Parameter 而不是 JSON body
            await apiClient.post(`/gmail/exchange-code?code=${encodeURIComponent(event.data.code)}`);
            showToast('Gmail 授權成功！', 'success');
            
            // 授權完成後，檢查授權狀態（使用輕量級檢查）
            setTimeout(() => {
              checkAuthorization();
            }, 1000);
          } catch (error: any) {
            showToast('交換授權碼失敗: ' + (error.response?.data?.detail || error.message), 'error');
          }
          
          setAuthorizing(false);
        } else if (event.data?.type === 'gmail_auth_error') {
          // 🔥 清理
          if (messageHandlerRef.current) {
            window.removeEventListener('message', messageHandlerRef.current);
            messageHandlerRef.current = null;
          }
          if (timeoutIdRef.current) {
            clearTimeout(timeoutIdRef.current);
            timeoutIdRef.current = null;
          }
          showToast('Gmail 授權失敗: ' + event.data.error, 'error');
          setAuthorizing(false);
        }
      };
      
      // 🔥 存儲引用
      messageHandlerRef.current = handleMessage;
      window.addEventListener('message', handleMessage);
      
      // 備用方案：如果 30 秒後還沒有收到消息，假設授權已完成
      timeoutIdRef.current = setTimeout(() => {
        if (messageHandlerRef.current) {
          window.removeEventListener('message', messageHandlerRef.current);
          messageHandlerRef.current = null;
        }
        checkAuthorization();
        setAuthorizing(false);
      }, 30000);
      
    } catch (error: any) {
      showToast('獲取授權 URL 失敗: ' + (error.response?.data?.detail || error.message), 'error');
      setAuthorizing(false);
    }
  };

  useEffect(() => {
    if (!visible) {
      // Modal 關閉時不做任何操作，只在清理函數中重置狀態
      return;
    }

    // Modal 打開時的邏輯
    if (token) {
      // 只有當 visible 為 true 且 token 可用時才檢查授權
      checkAuthorization();
    } else {
      // 如果 visible 為 true 但沒有 token，設置為未授權
      setIsAuthorized(false);
      setLoading(false); // 🔥 重置 loading
      setAuthorizing(false); // 🔥 重置 authorizing
    }
    
    // 🔥 當 Modal 打開時，重置選擇狀態
    setSelectedIds(new Set());
    setQuery('');
    setTags('');

    // 🔥 清理函數：移除所有事件監聽器和定時器，並重置狀態
    return () => {
      if (messageHandlerRef.current) {
        window.removeEventListener('message', messageHandlerRef.current);
        messageHandlerRef.current = null;
      }
      if (timeoutIdRef.current) {
        clearTimeout(timeoutIdRef.current);
        timeoutIdRef.current = null;
      }
      // 🔥 Modal 關閉時重置所有狀態
      setLoading(false);
      setAuthorizing(false);
      setImporting(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, token]); // 只依賴 visible 和 token

  const toggleSelect = (emailId: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(emailId)) {
      newSet.delete(emailId);
    } else {
      newSet.add(emailId);
    }
    setSelectedIds(newSet);
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === messages.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(messages.map(m => m.email_id)));
    }
  };

  const handleImport = async () => {
    if (selectedIds.size === 0) {
      showToast('請先選擇要導入的郵件', 'warning');
      return;
    }

    try {
      setImporting(true);
      const tagArray = tags.split(',').map(t => t.trim()).filter(t => t.length > 0);

      const response = await apiClient.post('/gmail/messages/batch-import', {
        email_ids: Array.from(selectedIds),
        tags: tagArray,
      });

      const { successful, failed } = response.data;
      showToast(`成功導入 ${successful} 個郵件${failed > 0 ? `, 失敗 ${failed} 個` : ''}`, 'success');

      setSelectedIds(new Set());
      setTags('');
      onSuccess?.(successful);
      
      // 導入成功後關閉彈窗
      onClose();
    } catch (error: any) {
      if (error.response?.status === 401) {
        // Gmail 未授權
        showToast('Gmail 未授權，請先完成授權', 'warning');
        setIsAuthorized(false);
      } else {
        showToast('導入郵件時出錯: ' + (error.response?.data?.detail || error.message), 'error');
      }
    } finally {
      setImporting(false);
    }
  };

  // 格式化日期
  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString('zh-TW', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
      });
    } catch {
      return dateString;
    }
  };

  // 格式化文件大小
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const closeModal = () => {
    if (!visible) return;
    onClose();
  };

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (authorizing || importing || loading) return;
    if (e.target === e.currentTarget) {
      closeModal();
    }
  };

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (event.key === 'Escape' && visible) {
      closeModal();
    }
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    document.addEventListener('keydown', handleKeyDown);
    const { style } = document.body;
    const originalOverflow = style.overflow;
    style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      style.overflow = originalOverflow;
    };
  }, [handleKeyDown, visible]);

  const modalContent = (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[1000]" onClick={handleOverlayClick}>
      <div className="bg-white border-3 border-neo-black shadow-neo-xl max-w-[900px] w-[95%] my-8 flex flex-col max-h-[90vh] overflow-hidden" 
           role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        
        {/* Header */}
        <header className="p-6 border-b-[3px] border-neo-black flex justify-between items-center bg-white">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white border-2 border-neo-black flex items-center justify-center shadow-neo-sm">
              <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 256 256"><path d="M224,48H32a8,8,0,0,0-8,8V192a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A8,8,0,0,0,224,48Zm-96,85.15L52.57,64H203.43ZM98.71,128,40,181.81V74.19Zm11.84,10.85,12,11.05a8,8,0,0,0,10.82,0l12-11.05,58,53.15H52.57ZM157.29,128,216,74.19V181.81Z"></path></svg>
            </div>
            <div>
              <h2 className="font-display text-2xl font-bold uppercase">Import from Gmail</h2>
              <p className="text-xs font-bold text-gray-500">郵件批次導入工具</p>
            </div>
          </div>
          <button 
            className="border-2 border-neo-black bg-neo-error text-white p-2 font-bold hover:shadow-neo-sm transition-all"
            onClick={closeModal}
            aria-label="關閉"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </header>

        {!isAuthorized ? (
          <div className="flex-1 flex flex-col items-center justify-center p-10 text-center">
            {(authorizing || loading) ? (
              <>
                <div className="flex justify-center items-start gap-3 mb-6 h-8">
                  <div className="w-6 h-6 bg-neo-primary border-2 border-neo-black neo-loader-dot-1"></div>
                  <div className="w-6 h-6 bg-neo-active border-2 border-neo-black neo-loader-dot-2"></div>
                  <div className="w-6 h-6 bg-neo-hover border-2 border-neo-black neo-loader-dot-3"></div>
                </div>
                <div className="w-20 h-20 border-3 border-neo-black bg-white shadow-neo-md mb-6 neo-spinner flex items-center justify-center">
                  <svg className="w-12 h-12" fill="currentColor" viewBox="0 0 256 256"><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216Zm40-68a28,28,0,0,1-28,28h-4v8a8,8,0,0,1-16,0v-8H104a8,8,0,0,1,0-16h36a12,12,0,0,0,0-24H116a28,28,0,0,1,0-56h4V72a8,8,0,0,1,16,0v8h16a8,8,0,0,1,0,16H116a12,12,0,0,0,0,24h24A28,28,0,0,1,168,148Z"></path></svg>
                </div>
                <p className="font-display text-xl font-bold uppercase text-neo-black">
                  {authorizing ? '正在打開授權窗口...' : '正在檢查授權狀態...'}
                </p>
                <p className="text-sm font-bold text-gray-500 mt-2">
                  {authorizing ? 'Opening Authorization Window' : 'Checking Auth Status'}
                </p>
              </>
            ) : (
              <>
                <div className="w-20 h-20 border-3 border-neo-black bg-neo-active flex items-center justify-center mb-6 shadow-neo-md">
                  <svg className="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 256 256"><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216Zm40-68a28,28,0,0,1-28,28h-4v8a8,8,0,0,1-16,0v-8H104a8,8,0,0,1,0-16h36a12,12,0,0,0,0-24H116a28,28,0,0,1,0-56h4V72a8,8,0,0,1,16,0v8h16a8,8,0,0,1,0,16H116a12,12,0,0,0,0,24h24A28,28,0,0,1,168,148Z"></path></svg>
                </div>
                <h3 className="font-display text-2xl font-bold uppercase mb-3">需要授權 Gmail 帳號</h3>
                <p className="text-gray-600 mb-8 font-medium">為了導入您的 Gmail 郵件，我們需要您的授權</p>
                <button
                  className="border-2 border-neo-black bg-neo-primary font-bold uppercase px-8 py-3 shadow-neo-md flex items-center gap-2 transition-all hover:bg-neo-hover hover:-translate-x-1 hover:-translate-y-1 hover:shadow-neo-lg active:translate-x-1 active:translate-y-1 active:shadow-none"
                  onClick={handleAuthorize}
                >
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 256 256"><path d="M224,48H32a8,8,0,0,0-8,8V192a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A8,8,0,0,0,224,48Zm-96,85.15L52.57,64H203.43ZM98.71,128,40,181.81V74.19Zm11.84,10.85,12,11.05a8,8,0,0,0,10.82,0l12-11.05,58,53.15H52.57ZM157.29,128,216,74.19V181.81Z"></path></svg>
                  使用 Google 帳號授權
                </button>
              </>
            )}
          </div>
        ) : (
          <>
            {/* Toolbar */}
            <div className="p-4 bg-gray-50 border-b-[3px] border-neo-black flex flex-col gap-4">
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                  <input
                    type="text"
                    placeholder="搜索主旨、寄件人..."
                    className="w-full border-2 border-neo-black pl-10 px-3 py-2 font-semibold outline-none transition-all focus:bg-green-50 focus:shadow-[3px_3px_0px_0px_#29bf12]"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && fetchMessages()}
                    disabled={loading}
                  />
                </div>
                <div className="flex items-center gap-2 border-2 border-neo-black bg-white px-3">
                  <span className="text-xs font-bold uppercase whitespace-nowrap">Load:</span>
                  <input
                    type="number"
                    value={limit}
                    onChange={(e) => setLimit(Math.min(100, Math.max(5, parseInt(e.target.value) || 25)))}
                    className="w-12 outline-none font-mono font-bold text-center border-b-2 border-gray-200 focus:border-neo-black"
                    min={5}
                    max={100}
                  />
                </div>
                <button
                  className={`border-2 border-neo-black bg-white font-bold uppercase px-4 py-2 shadow-neo-sm flex items-center gap-2 ${
                    loading ? 'opacity-50' : 'hover:bg-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-neo-md active:translate-x-1 active:translate-y-1 active:shadow-none'
                  }`}
                  onClick={fetchMessages}
                  disabled={loading}
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 256 256"><path d="M197.67,186.37a8,8,0,0,1,0,11.29C196.58,198.73,170.82,224,128,224c-37.39,0-64.53-22.34-80-39.85V208a8,8,0,0,1-16,0V160a8,8,0,0,1,8-8H88a8,8,0,0,1,0,16H55.44C67.76,183.35,93,208,128,208c36,0,58.14-21.46,58.36-21.68A8,8,0,0,1,197.67,186.37ZM216,40a8,8,0,0,0-8,8V71.85C192.53,54.34,165.39,32,128,32,85.18,32,59.42,57.27,58.34,58.34a8,8,0,0,0,11.3,11.3C69.86,69.46,92,48,128,48c35,0,60.24,24.65,72.56,40H168a8,8,0,0,0,0,16h48a8,8,0,0,0,8-8V48A8,8,0,0,0,216,40Z"></path></svg>
                  Refresh
                </button>
              </div>
            </div>

            {/* Mail List */}
            <div className="flex-1 overflow-y-auto bg-gray-100 p-4 space-y-3 gmail-importer-scroll">
              {loading ? (
                <div className="text-center py-20">
                  <div className="flex justify-center items-start gap-3 mb-6 h-8">
                    <div className="w-6 h-6 bg-neo-primary border-2 border-neo-black neo-loader-dot-1"></div>
                    <div className="w-6 h-6 bg-neo-active border-2 border-neo-black neo-loader-dot-2"></div>
                    <div className="w-6 h-6 bg-neo-hover border-2 border-neo-black neo-loader-dot-3"></div>
                  </div>
                  <div className="inline-block w-16 h-16 border-3 border-neo-black bg-white shadow-neo-md mb-4 neo-spinner flex items-center justify-center">
                    <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 256 256">
                      <path d="M224,48H32a8,8,0,0,0-8,8V192a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A8,8,0,0,0,224,48Zm-96,85.15L52.57,64H203.43ZM98.71,128,40,181.81V74.19Zm11.84,10.85,12,11.05a8,8,0,0,0,10.82,0l12-11.05,58,53.15H52.57ZM157.29,128,216,74.19V181.81Z"></path>
                    </svg>
                  </div>
                  <p className="font-display font-bold text-xl uppercase text-neo-black">載入郵件中...</p>
                  <p className="text-sm font-bold text-gray-500 mt-2">Loading Messages</p>
                </div>
              ) : messages.length === 0 ? (
                <div className="text-center py-20">
                  <div className="w-20 h-20 border-3 border-neo-black bg-gray-200 mx-auto mb-4 flex items-center justify-center">
                    <svg className="w-10 h-10 text-gray-400" fill="currentColor" viewBox="0 0 256 256"><path d="M224,48H32a8,8,0,0,0-8,8V192a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A8,8,0,0,0,224,48ZM203.43,64,128,133.15,52.57,64ZM216,192H40V74.19l82.59,75.71a8,8,0,0,0,10.82,0L216,74.19V192Z"></path></svg>
                  </div>
                  <p className="font-bold text-gray-500">沒有郵件</p>
                </div>
              ) : (
                messages.map((msg) => {
                  const isSelected = selectedIds.has(msg.email_id);
                  return (
                    <div
                      key={msg.email_id}
                      className={`border-2 border-gray-200 border-b-neo-black p-4 cursor-pointer transition-all bg-white flex gap-4 items-start ${
                        isSelected ? 'bg-green-50 !border-neo-primary shadow-[inset_4px_0_0_#29bf12]' : 'hover:bg-gray-50 hover:border-neo-black'
                      }`}
                      onClick={() => toggleSelect(msg.email_id)}
                    >
                      <div className={`w-5 h-5 border-2 border-neo-black bg-white flex items-center justify-center flex-shrink-0 mt-1 ${
                        isSelected ? 'bg-neo-primary' : ''
                      }`}>
                        {isSelected && <span className="text-black font-bold text-xs">✓</span>}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-start mb-1">
                          <span className="font-bold text-lg truncate pr-2">{msg.subject || '[無主題]'}</span>
                          {msg.is_unread && (
                            <span className="font-mono text-xs font-bold bg-neo-active text-white px-2 py-0.5 border border-neo-black whitespace-nowrap">UNREAD</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-xs font-mono text-gray-600 mb-2">
                          <span className="font-bold text-black">{msg.from_address}</span>
                          <span>•</span>
                          <span>{formatDate(msg.date)}</span>
                        </div>
                        <p className="text-sm text-gray-500 truncate">{msg.snippet}</p>
                      </div>
                      <div className="text-right flex flex-col items-end gap-2">
                        <span className="font-mono text-xs font-bold">{formatSize(msg.size)}</span>
                        {msg.is_starred && (
                          <span className="text-yellow-500">★</span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Footer */}
            {messages.length > 0 && (
              <footer className="p-4 border-t-[3px] border-neo-black bg-white flex justify-between items-center">
                <div className="flex items-center gap-2 cursor-pointer" onClick={toggleSelectAll}>
                  <div className={`w-5 h-5 border-2 border-neo-black flex items-center justify-center ${
                    selectedIds.size === messages.length && messages.length > 0 ? 'bg-neo-black' : 'bg-white'
                  }`}>
                    {selectedIds.size > 0 && selectedIds.size < messages.length ? (
                      <span className="text-white font-bold text-xs">−</span>
                    ) : selectedIds.size === messages.length && messages.length > 0 ? (
                      <span className="text-white font-bold text-xs">✓</span>
                    ) : null}
                  </div>
                  <span className="font-bold text-sm">Select All ({messages.length})</span>
                </div>
                <div className="flex gap-3 items-center">
                  <span className="text-sm font-bold text-gray-500">{selectedIds.size} selected</span>
                  <input
                    type="text"
                    placeholder="標籤 (用逗號分隔)"
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                    disabled={importing}
                    className="border-2 border-neo-black px-3 py-1 text-sm font-semibold outline-none w-48"
                  />
                  <button
                    className={`border-2 border-neo-black bg-neo-primary font-bold uppercase px-6 py-2 shadow-neo-md flex items-center gap-2 transition-all ${
                      importing || selectedIds.size === 0 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-neo-hover hover:-translate-x-1 hover:-translate-y-1 hover:shadow-neo-lg active:translate-x-1 active:translate-y-1 active:shadow-none'
                    }`}
                    onClick={handleImport}
                    disabled={importing || selectedIds.size === 0}
                  >
                    {importing ? (
                      <>
                        <svg className="w-5 h-5 neo-spin-icon" fill="currentColor" viewBox="0 0 256 256">
                          <path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,88-88A88.1,88.1,0,0,1,128,216Zm0-160V96a8,8,0,0,1-16,0V56a8,8,0,0,1,16,0Zm40,24a8,8,0,0,1,0,11.31l-28.28,28.28a8,8,0,0,1-11.31-11.31L156.69,80A8,8,0,0,1,168,80ZM200,120H160a8,8,0,0,1,0-16h40a8,8,0,0,1,0,16Z"></path>
                        </svg>
                        <span className="flex items-center gap-1">
                          Importing
                          <span className="inline-flex gap-0.5 ml-1">
                            <span className="inline-block w-1 h-1 bg-neo-black rounded-full neo-loader-dot-1"></span>
                            <span className="inline-block w-1 h-1 bg-neo-black rounded-full neo-loader-dot-2"></span>
                            <span className="inline-block w-1 h-1 bg-neo-black rounded-full neo-loader-dot-3"></span>
                          </span>
                        </span>
                      </>
                    ) : (
                      <>
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 256 256"><path d="M240,136v64a16,16,0,0,1-16,16H32a16,16,0,0,1-16-16V136a16,16,0,0,1,16-16H80a8,8,0,0,1,0,16H32v64H224V136H176a8,8,0,0,1,0-16h48A16,16,0,0,1,240,136Zm-117.66-2.34a8,8,0,0,0,11.32,0l48-48a8,8,0,0,0-11.32-11.32L136,108.69V24a8,8,0,0,0-16,0v84.69L85.66,74.34A8,8,0,0,0,74.34,85.66Z"></path></svg>
                        Import Files
                      </>
                    )}
                  </button>
                </div>
              </footer>
            )}
          </>
        )}
      </div>
    </div>
  );

  if (!visible) {
    return null;
  }

  return createPortal(modalContent, document.body);
}

export default GmailImporter;
