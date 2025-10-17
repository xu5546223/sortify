import React, { useState, useEffect } from 'react';
import { Modal, List, Checkbox, Button, Input, Spin, message, Tag, Empty, Space } from 'antd';
import { MailOutlined, LoadingOutlined, CheckCircleOutlined, UnlockOutlined } from '@ant-design/icons';
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

  // 檢查是否已授權
  const checkAuthorization = async () => {
    try {
      setLoading(true);
      // 使用輕量級端點檢查授權狀態，而不是獲取郵件列表
      const response = await apiClient.get('/gmail/check-auth-status');
      const { is_authorized } = response.data;
      
      if (is_authorized) {
        setIsAuthorized(true);
        // 授權後自動加載郵件列表
        await fetchMessages();
      } else {
        setIsAuthorized(false);
        setMessages([]);
      }
    } catch (error: any) {
      console.error('檢查授權狀態失敗:', error);
      setIsAuthorized(false);
      setMessages([]);
      // 不顯示錯誤提示，因為這只是狀態檢查
    } finally {
      setLoading(false);
    }
  };

  // 獲取授權 URL 並重定向
  const handleAuthorize = async () => {
    try {
      setAuthorizing(true);
      const response = await apiClient.get('/gmail/authorize-url');
      const { auth_url } = response.data;
      
      // 在新窗口中打開授權 URL
      const popup = window.open(auth_url, 'Gmail Authorization', 'width=500,height=600');
      
      if (!popup) {
        message.error('無法打開授權窗口。請檢查浏覽器彈出窗口設定');
        setAuthorizing(false);
        return;
      }
      
      // 使用 message 事件監聽授權完成
      const handleMessage = async (event: MessageEvent) => {
        // 驗證消息來源
        if (event.origin !== window.location.origin) return;
        
        if (event.data?.type === 'gmail_auth_complete' && event.data?.code) {
          window.removeEventListener('message', handleMessage);
          
          try {
            // 向後端發送 authorization code 進行交換
            // 改為使用 Query Parameter 而不是 JSON body
            await apiClient.post(`/gmail/exchange-code?code=${encodeURIComponent(event.data.code)}`);
            message.success('Gmail 授權成功！');
            
            // 授權完成後，檢查授權狀態（使用輕量級檢查）
            setTimeout(() => {
              checkAuthorization();
            }, 1000);
          } catch (error: any) {
            message.error('交換授權碼失敗: ' + (error.response?.data?.detail || error.message));
          }
          
          setAuthorizing(false);
        } else if (event.data?.type === 'gmail_auth_error') {
          window.removeEventListener('message', handleMessage);
          message.error('Gmail 授權失敗: ' + event.data.error);
          setAuthorizing(false);
        }
      };
      
      window.addEventListener('message', handleMessage);
      
      // 備用方案：如果 30 秒後還沒有收到消息，假設授權已完成
      setTimeout(() => {
        window.removeEventListener('message', handleMessage);
        checkAuthorization();
        setAuthorizing(false);
      }, 30000);
      
    } catch (error: any) {
      message.error('獲取授權 URL 失敗: ' + (error.response?.data?.detail || error.message));
      setAuthorizing(false);
    }
  };

  const fetchMessages = async () => {
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
        message.warning('Gmail 未授權，請先完成授權');
        setIsAuthorized(false);
      } else {
        message.error('無法獲取郵件列表: ' + (error.response?.data?.detail || error.message));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (visible && token) {
      // 只有當 visible 為 true 且 token 可用時才檢查授權
      checkAuthorization();
    } else if (visible && !token) {
      // 如果 visible 為 true 但沒有 token，設置為未授權
      setIsAuthorized(false);
    }
  }, [visible, token]);

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
      message.warning('請先選擇要導入的郵件');
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
      message.success(`成功導入 ${successful} 個郵件${failed > 0 ? `, 失敗 ${failed} 個` : ''}`);

      setSelectedIds(new Set());
      setTags('');
      onSuccess?.(successful);
      
      // 導入成功後關閉彈窗
      onClose();
    } catch (error: any) {
      if (error.response?.status === 401) {
        // Gmail 未授權
        message.warning('Gmail 未授權，請先完成授權');
        setIsAuthorized(false);
      } else {
        message.error('導入郵件時出錯: ' + (error.response?.data?.detail || error.message));
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

  return (
    <Modal
      title="📧 導入 Gmail 郵件"
      visible={visible}
      onCancel={onClose}
      width={800}
      footer={null}
      destroyOnClose
    >
      {!isAuthorized ? (
        <div className="gmail-importer-auth" style={{ textAlign: 'center', padding: '40px 20px' }}>
          <UnlockOutlined style={{ fontSize: 48, color: '#1890ff', marginBottom: 16 }} />
          <h3>需要授權 Gmail 帳號</h3>
          <p>為了導入您的 Gmail 郵件，我們需要您的授權</p>
          <Button
            type="primary"
            size="large"
            loading={authorizing}
            onClick={handleAuthorize}
            icon={<MailOutlined />}
          >
            使用 Google 帳號授權
          </Button>
        </div>
      ) : (
        <div className="gmail-importer">
          {/* 搜索欄 */}
          <div style={{ marginBottom: 16 }}>
            <Input
              placeholder="搜索郵件（例：from:someone@example.com）"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onPressEnter={fetchMessages}
              disabled={loading}
            />
            <Button
              type="primary"
              style={{ marginTop: 8, marginRight: 8 }}
              onClick={fetchMessages}
              loading={loading}
            >
              搜索
            </Button>
            <Button style={{ marginTop: 8 }} onClick={() => { setQuery(''); setMessages([]); }}>
              清除
            </Button>
          </div>

          {/* 讀取數量設定 */}
          <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
            <label style={{ fontSize: 14, whiteSpace: 'nowrap' }}>讀取郵件數量：</label>
            <input
              type="number"
              min={5}
              max={100}
              step={5}
              value={limit}
              onChange={(e) => setLimit(Math.min(100, Math.max(5, parseInt(e.target.value) || 25)))}
              style={{
                width: 80,
                padding: '6px 8px',
                border: '1px solid #d9d9d9',
                borderRadius: '4px',
                fontSize: 14
              }}
            />
            <span style={{ fontSize: 12, color: '#666' }}>封（5-100）</span>
            <Button
              size="small"
              onClick={() => {
                setQuery('');
                fetchMessages();
              }}
              loading={loading}
            >
              重新加載
            </Button>
          </div>

          {/* 郵件列表 */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px' }}>
              <Spin indicator={<LoadingOutlined style={{ fontSize: 48 }} />} />
            </div>
          ) : messages.length === 0 ? (
            <Empty description="沒有郵件" />
          ) : (
            <>
              <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Checkbox
                  indeterminate={selectedIds.size > 0 && selectedIds.size < messages.length}
                  checked={selectedIds.size === messages.length && messages.length > 0}
                  onChange={toggleSelectAll}
                >
                  全選
                </Checkbox>
                <span style={{ color: '#666' }}>
                  已選擇 {selectedIds.size} / {messages.length} 個郵件
                </span>
              </div>

              <List
                dataSource={messages}
                renderItem={(msg) => (
                  <List.Item
                    key={msg.email_id}
                    style={{
                      padding: '12px',
                      borderRadius: 4,
                      marginBottom: 8,
                      backgroundColor: '#fafafa',
                      cursor: 'pointer'
                    }}
                    onClick={() => toggleSelect(msg.email_id)}
                  >
                    <div style={{ width: '100%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <Checkbox
                          checked={selectedIds.has(msg.email_id)}
                          onChange={() => toggleSelect(msg.email_id)}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 500, marginBottom: 4 }}>
                            <MailOutlined style={{ marginRight: 8 }} />
                            {msg.subject || '[無主題]'}
                          </div>
                          <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>
                            {msg.from_address}
                          </div>
                          <div style={{ fontSize: 12, color: '#999' }}>
                            {msg.snippet}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right', minWidth: 120 }}>
                          <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>
                            {formatDate(msg.date)}
                          </div>
                          <div style={{ fontSize: 12, color: '#999' }}>
                            {formatSize(msg.size)}
                          </div>
                          <Space size="small" style={{ marginTop: 4 }}>
                            {msg.is_unread && <Tag color="blue">未讀</Tag>}
                            {msg.is_starred && <Tag color="gold">標星</Tag>}
                          </Space>
                        </div>
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            </>
          )}

          {/* 導入選項 */}
          {messages.length > 0 && (
            <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid #eee' }}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 8 }}>標籤 (用逗號分隔)</label>
                <Input
                  placeholder="例：郵件, 重要"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  disabled={importing}
                />
              </div>

              <div style={{ display: 'flex', gap: 8 }}>
                <Button onClick={onClose} disabled={importing}>
                  取消
                </Button>
                <Button
                  type="primary"
                  onClick={handleImport}
                  loading={importing}
                  disabled={selectedIds.size === 0}
                >
                  導入 {selectedIds.size} 個郵件
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default GmailImporter;
