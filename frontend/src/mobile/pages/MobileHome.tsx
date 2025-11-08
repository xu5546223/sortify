import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Modal, message, Tag } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { 
  CameraOutlined, 
  UploadOutlined, 
  ThunderboltOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  BulbOutlined,
  BankOutlined
} from '@ant-design/icons';
import { 
  triggerClustering, 
  getClusteringStatus
} from '../../services/clusteringService';
import suggestedQuestionsService from '../../services/suggestedQuestionsService';
import type { ClusteringJobStatus } from '../../types/apiTypes';
import type { SuggestedQuestion } from '../../types/suggestedQuestion';

const MobileHome: React.FC = () => {
  const navigate = useNavigate();
  const [showClusteringModal, setShowClusteringModal] = useState(false);
  const [jobStatus, setJobStatus] = useState<ClusteringJobStatus | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [generatingQuestions, setGeneratingQuestions] = useState(false);
  
  // 問題生成任務狀態
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [showProgressModal, setShowProgressModal] = useState(false);
  
  // 建議問題相關狀態
  const [suggestedQuestions, setSuggestedQuestions] = useState<SuggestedQuestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  // 獲取聚類狀態
  const fetchClusteringStatus = async () => {
    try {
      const status = await getClusteringStatus();
      setJobStatus(status);
    } catch (err: any) {
      // 404 表示沒有聚類任務,這是正常情況
      if (err.response?.status !== 404) {
        console.error('獲取聚類狀態失敗:', err);
      }
    }
  };

  // 載入建議問題
  const loadSuggestedQuestions = async () => {
    setLoadingSuggestions(true);
    try {
      const response = await suggestedQuestionsService.getSuggestedQuestions(3); // 只獲取3個問題
      setSuggestedQuestions(response.questions || []);
    } catch (error: any) {
      // 404 表示還沒有生成問題，這是正常情況
      if (error?.response?.status !== 404) {
        console.error('載入建議問題失敗:', error);
      }
    } finally {
      setLoadingSuggestions(false);
    }
  };

  // 處理問題點擊 - 跳轉到問答頁面
  const handleQuestionClick = async (question: SuggestedQuestion) => {
    try {
      // 標記為已使用
      await suggestedQuestionsService.markQuestionUsed(question.id);
      
      // 跳轉到問答頁面並填入問題
      navigate('/mobile/qa', { 
        state: { 
          prefilledQuestion: question.question,
          fromQuestionBank: true
        } 
      });
    } catch (error) {
      console.error('標記問題失敗:', error);
      // 即使標記失敗，也繼續跳轉
      navigate('/mobile/qa', { 
        state: { 
          prefilledQuestion: question.question,
          fromQuestionBank: true
        } 
      });
    }
  };

  // 組件掛載時獲取狀態和建議問題
  useEffect(() => {
    fetchClusteringStatus();
    loadSuggestedQuestions();
  }, []);

  // 觸發聚類
  const handleTriggerClustering = async () => {
    setIsTriggering(true);
    try {
      const result = await triggerClustering();
      setJobStatus(result);
      message.success('智能分類已啟動！', 2);
      
      // 開始輪詢狀態
      startPolling();
    } catch (err: any) {
      console.error('觸發聚類失敗:', err);
      message.error(err.response?.data?.detail || '觸發聚類失敗');
    } finally {
      setIsTriggering(false);
    }
  };

  // 輪詢狀態更新
  const startPolling = () => {
    const pollInterval = setInterval(async () => {
      try {
        const status = await getClusteringStatus();
        setJobStatus(status);
        
        if (status && (status.status === 'completed' || status.status === 'failed')) {
          clearInterval(pollInterval);
          if (status.status === 'completed') {
            message.success(`分類完成！生成 ${status.clusters_created} 個分類`, 3);
          }
        }
      } catch (err) {
        clearInterval(pollInterval);
      }
    }, 2000);

    // 最多輪詢5分鐘
    setTimeout(() => clearInterval(pollInterval), 300000);
  };

  // 獲取狀態圖標
  const getStatusIcon = () => {
    if (!jobStatus) return null;

    switch (jobStatus.status) {
      case 'running':
        return <ReloadOutlined spin style={{ color: '#1890ff' }} />;
      case 'completed':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'failed':
        return <ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />;
      case 'pending':
        return <ClockCircleOutlined style={{ color: '#faad14' }} />;
      default:
        return null;
    }
  };

  const getStatusText = () => {
    if (!jobStatus) return '尚未執行聚類';

    switch (jobStatus.status) {
      case 'running':
        return '正在執行聚類...';
      case 'completed':
        return `聚類完成 - 生成 ${jobStatus.clusters_created} 個分類`;
      case 'failed':
        return `聚類失敗: ${jobStatus.error_message || '未知錯誤'}`;
      case 'pending':
        return '聚類任務排隊中...';
      default:
        return '未知狀態';
    }
  };

  // 顯示生成問題預估 Modal
  const showGenerateQuestionModal = () => {
    Modal.confirm({
      title: '生成智能問題',
      content: (
        <div style={{ padding: '12px 0' }}>
          <div style={{ marginBottom: '16px', fontSize: '14px', color: '#595959', lineHeight: '1.6' }}>
            系統將根據您的文檔分類，智能生成個性化問題：
          </div>
          <div style={{ 
            background: '#f0f5ff', 
            padding: '12px', 
            borderRadius: '6px',
            marginBottom: '16px',
            border: '1px solid #d6e4ff'
          }}>
            <div style={{ fontSize: '13px', color: '#0050b3', marginBottom: '8px' }}>
              <strong>📊 預計生成：</strong>
            </div>
            <ul style={{ 
              margin: 0, 
              paddingLeft: '20px', 
              fontSize: '12px', 
              color: '#0050b3',
              lineHeight: '1.8'
            }}>
              <li>每個分類 5 個問題</li>
              <li>3 個時間相關問題</li>
            </ul>
            <div style={{ 
              marginTop: '12px', 
              fontSize: '13px', 
              color: '#0050b3',
              fontWeight: 600,
              textAlign: 'center',
              padding: '8px',
              background: 'white',
              borderRadius: '4px'
            }}>
              總計約 {jobStatus?.clusters_created ? (jobStatus.clusters_created * 5 + 3) : '10-30'} 個問題
            </div>
          </div>
          <div style={{ fontSize: '12px', color: '#8c8c8c', textAlign: 'center' }}>
            💡 生成完成後可在「智能建議問題」中查看
          </div>
        </div>
      ),
      okText: '開始生成',
      cancelText: '取消',
      centered: true,
      width: '90%',
      style: { maxWidth: '400px' },
      onOk: handleGenerateQuestions
    });
  };

  // 生成智能問題（非阻塞）
  const handleGenerateQuestions = async () => {
    try {
      setGeneratingQuestions(true);
      
      // 啟動生成任務
      const response = await suggestedQuestionsService.generateSuggestedQuestions({
        force_regenerate: true,
        questions_per_category: 5,
        include_cross_category: false  // 已停用跨分類問題生成
      });
      
      if (!response.task_id) {
        throw new Error('未獲取到任務ID');
      }
      
      // 保存任務 ID 到 localStorage
      localStorage.setItem('question_generation_task_id', response.task_id);
      setCurrentTaskId(response.task_id);
      
      message.success({
        content: '問題生成任務已啟動，您可以繼續使用其他功能',
        duration: 3
      });
      
      setGeneratingQuestions(false);
      
    } catch (err: any) {
      setGeneratingQuestions(false);
      
      const errorMsg = err?.response?.data?.detail || '生成建議問題失敗';
      
      // 提供更友好的錯誤提示
      if (errorMsg.includes('聚類') || errorMsg.includes('分類') || errorMsg.includes('沒有聚類信息')) {
          Modal.info({
            title: '需要先執行智能分類',
            content: (
              <div style={{ padding: '12px 0' }}>
                <div style={{ marginBottom: '16px', fontSize: '14px', lineHeight: '1.6' }}>
                  生成智能問題需要先完成文檔分類。
                </div>
                <div style={{ 
                  background: '#fff7e6', 
                  padding: '12px', 
                  borderRadius: '6px',
                  border: '1px solid #ffd591',
                  marginBottom: '16px'
                }}>
                  <div style={{ fontSize: '13px', color: '#d46b08', marginBottom: '8px' }}>
                    <strong>📋 前置條件：</strong>
                  </div>
                  <ul style={{ 
                    margin: 0, 
                    paddingLeft: '20px', 
                    fontSize: '12px', 
                    color: '#d46b08',
                    lineHeight: '1.8'
                  }}>
                    <li>至少上傳 20 個文檔</li>
                    <li>執行「智能分類」功能</li>
                    <li>等待分類完成</li>
                  </ul>
                </div>
                <div style={{ fontSize: '12px', color: '#8c8c8c', textAlign: 'center' }}>
                  💡 完成分類後即可生成個性化問題
                </div>
              </div>
            ),
            okText: '我知道了',
            centered: true,
            width: '90%',
            style: { maxWidth: '400px' }
          });
      } else if (errorMsg.includes('文檔')) {
        message.error({
          content: '文檔數量不足，請先上傳更多文檔',
          duration: 4
        });
      } else {
        message.error(errorMsg);
      }
      
      console.error('生成智能問題失敗:', err);
    }
  };

  // 查看生成進度
  const handleViewProgress = async () => {
    const taskId = currentTaskId || localStorage.getItem('question_generation_task_id');
    
    if (!taskId) {
      message.info('目前沒有正在執行的生成任務');
      return;
    }
    
    setShowProgressModal(true);
    
    // 創建進度 Modal
    const progressModal = Modal.info({
      title: '問題生成進度',
      content: (
        <div style={{ padding: '12px 0' }}>
          <div style={{ marginBottom: '16px' }}>
            <div style={{ 
              height: '8px', 
              background: '#f0f0f0', 
              borderRadius: '4px',
              overflow: 'hidden'
            }}>
              <div 
                id="progress-bar-view"
                style={{ 
                  height: '100%', 
                  background: '#1890ff',
                  width: '0%',
                  transition: 'width 0.3s'
                }} 
              />
            </div>
            <div 
              id="progress-text-view"
              style={{ 
                marginTop: '8px', 
                fontSize: '12px', 
                color: '#666',
                textAlign: 'center'
              }}
            >
              載入中...
            </div>
          </div>
        </div>
      ),
      okText: '關閉',
      centered: true,
      width: '90%',
      style: { maxWidth: '400px' },
      onOk: () => {
        setShowProgressModal(false);
      }
    });
    
    try {
      // 導入 taskService
      const { default: taskService } = await import('../../services/taskService');
      
      // 輪詢任務狀態
      await taskService.pollTaskStatus(taskId, {
        onProgress: (status) => {
          // 更新進度條
          const progressBar = document.getElementById('progress-bar-view');
          const progressText = document.getElementById('progress-text-view');
          
          if (progressBar) {
            progressBar.style.width = `${status.progress}%`;
          }
          
          if (progressText) {
            progressText.textContent = `${status.current_step} (${status.progress}%)`;
          }
        },
        onComplete: async (status) => {
          progressModal.destroy();
          setShowProgressModal(false);
          
          // 清除任務 ID
          localStorage.removeItem('question_generation_task_id');
          setCurrentTaskId(null);
          
          message.success({
            content: `成功生成 ${status.result?.total_questions || 0} 個智能問題！`,
            duration: 3
          });
          
          // 重新載入建議問題
          await loadSuggestedQuestions();
        },
        onError: (error) => {
          progressModal.destroy();
          setShowProgressModal(false);
          
          // 清除任務 ID
          localStorage.removeItem('question_generation_task_id');
          setCurrentTaskId(null);
          
          message.error(error);
        }
      });
      
    } catch (err: any) {
      progressModal.destroy();
      setShowProgressModal(false);
      message.error('查詢任務狀態失敗');
      console.error('查詢任務狀態失敗:', err);
    }
  };

  // 組件加載時檢查是否有未完成的任務
  useEffect(() => {
    const checkOngoingTask = async () => {
      const taskId = localStorage.getItem('question_generation_task_id');
      if (taskId) {
        try {
          const { default: taskService } = await import('../../services/taskService');
          const status = await taskService.getTaskStatus(taskId);
          
          if (status.status === 'completed') {
            // 任務已完成，清除並刷新
            localStorage.removeItem('question_generation_task_id');
            await loadSuggestedQuestions();
          } else if (status.status === 'failed') {
            // 任務失敗，清除
            localStorage.removeItem('question_generation_task_id');
          } else {
            // 任務進行中，設置狀態
            setCurrentTaskId(taskId);
          }
        } catch (error) {
          // 任務不存在或已過期，清除
          localStorage.removeItem('question_generation_task_id');
        }
      }
    };
    
    checkOngoingTask();
  }, []);

  const quickActions = [
    {
      icon: <CameraOutlined />,
      label: '拍照上傳',
      color: '#29bf12',
      onClick: () => navigate('/mobile/camera')
    },
    {
      icon: <UploadOutlined />,
      label: '選擇文件',
      color: '#08bdbdff',
      onClick: () => navigate('/mobile/upload')
    },
    {
      icon: <ThunderboltOutlined />,
      label: '智能分類',
      color: '#9c27b0',
      onClick: () => setShowClusteringModal(true)
    },
    {
      icon: <BulbOutlined />,
      label: '生成問題',
      color: '#ff9800',
      onClick: showGenerateQuestionModal,
      loading: generatingQuestions
    }
  ];

  return (
    <>
      <MobileHeader title="Sortify AI" />
      
      <div className="mobile-fade-in" style={{ 
        padding: '24px 16px',
        paddingBottom: 'calc(var(--mobile-bottom-nav-height) + max(24px, env(safe-area-inset-bottom)))',
        maxWidth: '100vw',
        overflowX: 'hidden'
      }}>
        <div className="mobile-card">
          <h2 style={{ 
            fontSize: 'min(24px, 6vw)', 
            fontWeight: '700', 
            margin: '0 0 8px 0',
            wordWrap: 'break-word'
          }}>
            歡迎使用 Sortify AI
          </h2>
          <p style={{ 
            fontSize: 'min(14px, 3.5vw)', 
            color: '#666', 
            margin: 0 
          }}>
            智能文件分析和問答助手
          </p>
        </div>

        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <h3 className="mobile-card-title">快速操作</h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: 'min(16px, 4vw)'
          }}>
            {quickActions.map((action, index) => (
              <div
                key={index}
                onClick={action.onClick}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '12px',
                  padding: 'min(24px, 5vw) min(16px, 4vw)',
                  borderRadius: '12px',
                  backgroundColor: '#f8f9fa',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  minHeight: '100px',
                  justifyContent: 'center'
                }}
                onTouchStart={(e) => {
                  (e.currentTarget as HTMLDivElement).style.transform = 'scale(0.95)';
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = '#e8e9ea';
                }}
                onTouchEnd={(e) => {
                  (e.currentTarget as HTMLDivElement).style.transform = 'scale(1)';
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = '#f8f9fa';
                }}
                onTouchCancel={(e) => {
                  (e.currentTarget as HTMLDivElement).style.transform = 'scale(1)';
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = '#f8f9fa';
                }}
              >
                <div style={{
                  fontSize: 'min(32px, 8vw)',
                  color: action.color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}>
                  {action.loading ? <ReloadOutlined spin /> : action.icon}
                </div>
                <span style={{
                  fontSize: 'min(14px, 3.5vw)',
                  fontWeight: '500',
                  textAlign: 'center',
                  wordWrap: 'break-word'
                }}>
                  {action.label}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 智能建議問題卡片 */}
        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            marginBottom: '16px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h3 className="mobile-card-title" style={{ margin: 0 }}>💡 智能建議問題</h3>
              {/* 如果有正在執行的任務，顯示進度指示器 */}
              {currentTaskId && (
                <span style={{
                  fontSize: '11px',
                  color: '#52c41a',
                  background: '#f6ffed',
                  border: '1px solid #b7eb8f',
                  borderRadius: '12px',
                  padding: '2px 8px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}>
                  <ClockCircleOutlined spin style={{ fontSize: '10px' }} />
                  生成中
                </span>
              )}
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {/* 如果有任務，添加查看進度按鈕 */}
              {currentTaskId && (
                <button
                  onClick={handleViewProgress}
                  style={{
                    padding: '4px 12px',
                    fontSize: '11px',
                    color: '#52c41a',
                    background: 'transparent',
                    border: '1px solid #52c41a',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  查看進度
                </button>
              )}
              <button
                onClick={loadSuggestedQuestions}
                disabled={loadingSuggestions}
                style={{
                  padding: '4px 12px',
                  fontSize: '12px',
                  color: '#1890ff',
                  background: 'transparent',
                  border: '1px solid #1890ff',
                  borderRadius: '6px',
                  cursor: loadingSuggestions ? 'not-allowed' : 'pointer',
                  opacity: loadingSuggestions ? 0.6 : 1
                }}
              >
                {loadingSuggestions ? <ReloadOutlined spin /> : '🔄'}
              </button>
            </div>
          </div>

          {loadingSuggestions ? (
            <div style={{ 
              textAlign: 'center', 
              padding: '20px', 
              color: '#999',
              fontSize: '13px' 
            }}>
              載入中...
            </div>
          ) : suggestedQuestions.length > 0 ? (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {suggestedQuestions.map((question, index) => (
                  <div
                    key={question.id}
                    onClick={() => handleQuestionClick(question)}
                    style={{
                      padding: '12px',
                      background: '#f8f9fa',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      border: '1px solid #e8e9ea',
                      position: 'relative'
                    }}
                    onTouchStart={(e) => {
                      (e.currentTarget as HTMLDivElement).style.transform = 'scale(0.98)';
                      (e.currentTarget as HTMLDivElement).style.background = '#e8e9ea';
                    }}
                    onTouchEnd={(e) => {
                      (e.currentTarget as HTMLDivElement).style.transform = 'scale(1)';
                      (e.currentTarget as HTMLDivElement).style.background = '#f8f9fa';
                    }}
                    onTouchCancel={(e) => {
                      (e.currentTarget as HTMLDivElement).style.transform = 'scale(1)';
                      (e.currentTarget as HTMLDivElement).style.background = '#f8f9fa';
                    }}
                  >
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'flex-start',
                      gap: '8px',
                      marginBottom: '8px'
                    }}>
                      <span style={{ 
                        fontSize: '16px',
                        flexShrink: 0,
                        marginTop: '2px'
                      }}>
                        📌
                      </span>
                      <div style={{ 
                        flex: 1,
                        fontSize: '14px',
                        color: '#333',
                        lineHeight: '1.5',
                        fontWeight: '500'
                      }}>
                        {question.question}
                      </div>
                    </div>
                    
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center',
                      gap: '8px',
                      paddingLeft: '24px',
                      flexWrap: 'wrap'
                    }}>
                      {question.category && (
                        <Tag 
                          color="blue" 
                          style={{ 
                            fontSize: '11px',
                            margin: 0,
                            padding: '2px 8px',
                            borderRadius: '4px'
                          }}
                        >
                          🏷️ {question.category}
                        </Tag>
                      )}
                      {question.is_cross_category && (
                        <Tag 
                          color="purple" 
                          style={{ 
                            fontSize: '11px',
                            margin: 0,
                            padding: '2px 8px',
                            borderRadius: '4px'
                          }}
                        >
                          🌐 跨分類
                        </Tag>
                      )}
                      <span style={{ 
                        fontSize: '11px', 
                        color: question.use_count > 0 ? '#999' : '#29bf12',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px'
                      }}>
                        {question.use_count > 0 ? (
                          <>⏰ 已使用 {question.use_count} 次</>
                        ) : (
                          <>✨ 未使用</>
                        )}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ 
                marginTop: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
              }}>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => navigate('/mobile/question-bank')}
                    style={{
                      flex: 1,
                      padding: '10px',
                      fontSize: '13px',
                      color: '#1890ff',
                      background: 'white',
                      border: '1px solid #1890ff',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: '500'
                    }}
                  >
                    查看更多問題 →
                  </button>
                  <button
                    onClick={showGenerateQuestionModal}
                    disabled={generatingQuestions}
                    style={{
                      flex: 1,
                      padding: '10px',
                      fontSize: '13px',
                      color: 'white',
                      background: generatingQuestions ? '#ccc' : '#ff9800',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: generatingQuestions ? 'not-allowed' : 'pointer',
                      fontWeight: '500'
                    }}
                  >
                    {generatingQuestions ? <ReloadOutlined spin /> : '🔄 重新生成'}
                  </button>
                </div>
                
                {/* 如果有正在執行的任務，顯示查看進度按鈕 */}
                {currentTaskId && (
                  <button
                    onClick={handleViewProgress}
                    style={{
                      width: '100%',
                      padding: '10px',
                      fontSize: '13px',
                      color: '#52c41a',
                      background: 'white',
                      border: '1px solid #52c41a',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: '500',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '6px'
                    }}
                  >
                    <ClockCircleOutlined spin />
                    查看生成進度
                  </button>
                )}
              </div>
            </>
          ) : (
            <div style={{ 
              textAlign: 'center', 
              padding: '24px 16px',
              background: '#f8f9fa',
              borderRadius: '8px'
            }}>
              <div style={{ fontSize: '32px', marginBottom: '12px' }}>💭</div>
              <div style={{ 
                fontSize: '14px', 
                color: '#666',
                marginBottom: '16px',
                lineHeight: '1.6'
              }}>
                還沒有建議問題<br/>
                請先執行智能分類後生成問題
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
                <button
                  onClick={showGenerateQuestionModal}
                  disabled={generatingQuestions}
                  style={{
                    padding: '10px 20px',
                    fontSize: '13px',
                    color: 'white',
                    background: generatingQuestions ? '#ccc' : '#ff9800',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: generatingQuestions ? 'not-allowed' : 'pointer',
                    fontWeight: '500'
                  }}
                >
                  {generatingQuestions ? <ReloadOutlined spin /> : '立即生成問題'}
                </button>
                
                {/* 如果有正在執行的任務，顯示查看進度按鈕 */}
                {currentTaskId && (
                  <button
                    onClick={handleViewProgress}
                    style={{
                      padding: '10px 20px',
                      fontSize: '13px',
                      color: '#52c41a',
                      background: 'white',
                      border: '1px solid #52c41a',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: '500',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '6px'
                    }}
                  >
                    <ClockCircleOutlined spin />
                    查看生成進度
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* 使用提示 */}
        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <h3 className="mobile-card-title">💡 使用指南</h3>
          <div style={{ fontSize: '13px', color: '#666', lineHeight: '1.8' }}>
            <div style={{ marginBottom: '12px', paddingBottom: '12px', borderBottom: '1px solid #f0f0f0' }}>
              <div style={{ fontWeight: 600, color: '#333', marginBottom: '6px', fontSize: '14px' }}>
                📸 文檔上傳與分析
              </div>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                <li style={{ marginBottom: '6px' }}>拍照或上傳文件後，系統會自動進行 AI 分析</li>
                <li style={{ marginBottom: '6px' }}>分析完成後自動向量化，支援智能問答</li>
              </ul>
            </div>
            
            <div style={{ marginBottom: '12px', paddingBottom: '12px', borderBottom: '1px solid #f0f0f0' }}>
              <div style={{ fontWeight: 600, color: '#333', marginBottom: '6px', fontSize: '14px' }}>
                ⚡ 智能分類與問題生成
              </div>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                <li style={{ marginBottom: '6px' }}>累積 <strong style={{ color: '#29bf12' }}>20 個以上</strong>文件後，可執行智能分類</li>
                <li style={{ marginBottom: '6px' }}>分類完成後，點擊「生成問題」智能產生問題庫</li>
                <li style={{ marginBottom: '6px' }}>系統會根據分類自動生成相關問題供您參考</li>
              </ul>
            </div>
            
            <div>
              <div style={{ fontWeight: 600, color: '#333', marginBottom: '6px', fontSize: '14px' }}>
                💬 智能問答
              </div>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                <li style={{ marginBottom: '6px' }}>點擊建議問題可直接跳轉到問答頁面</li>
                <li style={{ marginBottom: '6px' }}>支援文檔搜索、跨文檔分析等功能</li>
                <li style={{ marginBottom: '6px' }}>AI 會根據您的問題自動選擇相關文檔</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* 智能分類 Modal */}
      <Modal
        title={null}
        open={showClusteringModal}
        onCancel={() => setShowClusteringModal(false)}
        footer={null}
        centered
        width="90%"
        style={{ maxWidth: '400px' }}
      >
        <div style={{ padding: '12px 0' }}>
          {/* 標題 */}
          <div style={{ 
            textAlign: 'center', 
            marginBottom: '20px',
            paddingBottom: '16px',
            borderBottom: '1px solid #f0f0f0'
          }}>
            <div style={{ fontSize: '32px', marginBottom: '8px' }}>
              ⚡
            </div>
            <h3 style={{ 
              fontSize: '20px', 
              fontWeight: '600', 
              margin: '0 0 8px 0' 
            }}>
              智能分類
            </h3>
            <p style={{ 
              fontSize: '13px', 
              color: '#666', 
              margin: 0 
            }}>
              自動分析文檔並生成動態分類
            </p>
          </div>

          {/* 執行按鈕 */}
          <button
            onClick={handleTriggerClustering}
            disabled={isTriggering || jobStatus?.status === 'running'}
            className="mobile-btn mobile-btn-primary"
            style={{
              width: '100%',
              background: isTriggering || jobStatus?.status === 'running' 
                ? '#d9d9d9' 
                : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              border: 'none',
              marginBottom: '16px'
            }}
          >
            <ThunderboltOutlined style={{ marginRight: '8px' }} />
            {isTriggering ? '啟動中...' : '執行智能分類'}
          </button>

          {/* 狀態顯示 */}
          {jobStatus && (
            <div style={{
              padding: '16px',
              backgroundColor: '#f8f9fa',
              borderRadius: '12px',
              marginBottom: '16px'
            }}>
              {/* 狀態標題 */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '12px'
              }}>
                <span style={{ fontSize: '20px' }}>
                  {getStatusIcon()}
                </span>
                <span style={{
                  fontSize: '14px',
                  fontWeight: '500',
                  color: '#333'
                }}>
                  {getStatusText()}
                </span>
              </div>

              {/* 處理中提示 */}
              {jobStatus.status === 'running' && (
                <div style={{
                  padding: '16px',
                  textAlign: 'center',
                  backgroundColor: '#fff',
                  borderRadius: '8px',
                  marginBottom: '12px'
                }}>
                  <div style={{
                    fontSize: '14px',
                    color: '#1890ff',
                    marginBottom: '8px'
                  }}>
                    ⏳ 正在後台處理中...
                  </div>
                  <div style={{
                    fontSize: '12px',
                    color: '#999'
                  }}>
                    智能分析文檔內容並生成分類
                  </div>
                </div>
              )}

              {/* 完成統計 */}
              {jobStatus.status === 'completed' && (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '12px',
                  marginTop: '12px'
                }}>
                  <div style={{
                    padding: '12px',
                    backgroundColor: '#fff',
                    borderRadius: '8px',
                    textAlign: 'center'
                  }}>
                    <div style={{ 
                      fontSize: '12px', 
                      color: '#666',
                      marginBottom: '4px'
                    }}>
                      處理文檔
                    </div>
                    <div style={{ 
                      fontSize: '20px', 
                      fontWeight: '600',
                      color: '#333'
                    }}>
                      {jobStatus.total_documents}
                    </div>
                  </div>
                  <div style={{
                    padding: '12px',
                    backgroundColor: '#fff',
                    borderRadius: '8px',
                    textAlign: 'center'
                  }}>
                    <div style={{ 
                      fontSize: '12px', 
                      color: '#666',
                      marginBottom: '4px'
                    }}>
                      生成分類
                    </div>
                    <div style={{ 
                      fontSize: '20px', 
                      fontWeight: '600',
                      color: '#333'
                    }}>
                      {jobStatus.clusters_created}
                    </div>
                  </div>
                </div>
              )}

              {/* 時間信息 */}
              {jobStatus.started_at && (
                <div style={{
                  marginTop: '12px',
                  fontSize: '11px',
                  color: '#999',
                  lineHeight: '1.5'
                }}>
                  <div>開始: {new Date(jobStatus.started_at).toLocaleString('zh-TW')}</div>
                  {jobStatus.completed_at && (
                    <div>完成: {new Date(jobStatus.completed_at).toLocaleString('zh-TW')}</div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 說明文字 */}
          <div style={{
            padding: '12px',
            backgroundColor: '#e6f7ff',
            borderRadius: '8px',
            border: '1px solid #91d5ff'
          }}>
            <div style={{ 
              fontSize: '13px', 
              color: '#0050b3',
              lineHeight: '1.6'
            }}>
              <div style={{ marginBottom: '6px' }}>
                💡 <strong>智能分類功能說明：</strong>
              </div>
              <ul style={{ 
                margin: 0, 
                paddingLeft: '20px',
                fontSize: '12px'
              }}>
                <li>自動分析您的文檔內容</li>
                <li>使用 AI 生成動態分類</li>
                <li>建議累積 20 個以上文檔後執行</li>
                <li>分類結果可在文件列表中查看</li>
              </ul>
            </div>
          </div>

          {/* 查看結果按鈕 */}
          {jobStatus?.status === 'completed' && (
            <button
              onClick={() => {
                setShowClusteringModal(false);
                navigate('/mobile/documents');
              }}
              className="mobile-btn mobile-btn-secondary"
              style={{
                width: '100%',
                marginTop: '16px'
              }}
            >
              查看分類結果
            </button>
          )}
        </div>
      </Modal>
    </>
  );
};

export default MobileHome;

