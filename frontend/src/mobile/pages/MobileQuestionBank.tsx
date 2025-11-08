import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Tabs, 
  Input, 
  Empty, 
  Spin, 
  Tag, 
  Button, 
  message,
  Modal,
  Badge,
  Pagination
} from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  ThunderboltOutlined,
  GlobalOutlined,
  FolderOutlined,
  QuestionCircleOutlined,
  LeftOutlined,
  RightOutlined
} from '@ant-design/icons';
import MobileHeader from '../components/MobileHeader';
import suggestedQuestionsService from '../../services/suggestedQuestionsService';
import type { SuggestedQuestion } from '../../types/suggestedQuestion';
import '../../styles/mobile-question-bank.css';

const { TabPane } = Tabs;

interface QuestionStats {
  total: number;
  unused: number;
  used: number;
  categories: { [key: string]: number };
}

const MobileQuestionBank: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [questions, setQuestions] = useState<SuggestedQuestion[]>([]);
  const [filteredQuestions, setFilteredQuestions] = useState<SuggestedQuestion[]>([]);
  const [paginatedQuestions, setPaginatedQuestions] = useState<SuggestedQuestion[]>([]);
  const [searchText, setSearchText] = useState('');
  const [activeTab, setActiveTab] = useState('all');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 5; // 每頁5個問題
  const [stats, setStats] = useState<QuestionStats>({
    total: 0,
    unused: 0,
    used: 0,
    categories: {}
  });

  // 載入所有問題
  const loadQuestions = async () => {
    setLoading(true);
    try {
      const response = await suggestedQuestionsService.getAllSuggestedQuestions();
      const allQuestions = response.questions || [];
      setQuestions(allQuestions);
      calculateStats(allQuestions);
      filterQuestions(allQuestions, activeTab, searchText);
    } catch (error: any) {
      if (error?.response?.status === 404) {
        setQuestions([]);
        setFilteredQuestions([]);
        calculateStats([]);
      } else {
        console.error('載入問題失敗:', error);
        message.error('載入問題失敗，請稍後再試');
      }
    } finally {
      setLoading(false);
    }
  };

  // 計算統計數據
  const calculateStats = (questionList: SuggestedQuestion[]) => {
    const categories: { [key: string]: number } = {};
    let used = 0;
    
    questionList.forEach(q => {
      if (q.use_count > 0) used++;
      if (q.category) {
        categories[q.category] = (categories[q.category] || 0) + 1;
      }
    });

    // 調試日誌
    console.log('📊 統計數據:', {
      total: questionList.length,
      used,
      unused: questionList.length - used,
      categories,
      sampleQuestions: questionList.slice(0, 3).map(q => ({
        question: q.question.substring(0, 30) + '...',
        category: q.category,
        is_cross_category: q.is_cross_category
      }))
    });

    setStats({
      total: questionList.length,
      unused: questionList.length - used,
      used: used,
      categories
    });
  };

  // 過濾問題
  const filterQuestions = (
    questionList: SuggestedQuestion[], 
    tab: string, 
    search: string
  ) => {
    let filtered = [...questionList];

    // 根據標籤頁過濾
    if (tab === 'unused') {
      filtered = filtered.filter(q => q.use_count === 0);
    } else if (tab === 'used') {
      filtered = filtered.filter(q => q.use_count > 0);
    } else if (tab.startsWith('category_')) {
      const categoryName = tab.replace('category_', '');
      filtered = filtered.filter(q => q.category === categoryName);
    }

    // 根據搜索文本過濾
    if (search.trim()) {
      const searchLower = search.toLowerCase().trim();
      filtered = filtered.filter(q => 
        q.question.toLowerCase().includes(searchLower) ||
        q.category?.toLowerCase().includes(searchLower)
      );
    }

    // 按使用次數和時間排序（未使用的在前，最近使用的在後）
    filtered.sort((a, b) => {
      if (a.use_count === 0 && b.use_count > 0) return -1;
      if (a.use_count > 0 && b.use_count === 0) return 1;
      if (a.last_used_at && b.last_used_at) {
        return new Date(b.last_used_at).getTime() - new Date(a.last_used_at).getTime();
      }
      return 0;
    });

    setFilteredQuestions(filtered);
  };

  // 刷新問題庫
  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      message.loading({ content: '正在重新生成問題...', key: 'refresh', duration: 0 });
      
      await suggestedQuestionsService.generateSuggestedQuestions({
        force_regenerate: true,
        questions_per_category: 5,
        include_cross_category: true
      });
      
      message.destroy('refresh');
      message.success('問題庫已更新！');
      
      await loadQuestions();
    } catch (error: any) {
      message.destroy('refresh');
      const errorMsg = error?.response?.data?.detail || '刷新失敗';
      message.error(errorMsg);
      console.error('刷新問題失敗:', error);
    } finally {
      setRefreshing(false);
    }
  };

  // 點擊問題 - 跳轉到問答頁面
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

  // 獲取問題類型圖標
  const getQuestionTypeIcon = (type: string) => {
    switch (type) {
      case 'cross_category':
        return <GlobalOutlined />;
      case 'time_based':
        return <ClockCircleOutlined />;
      case 'category':
        return <FolderOutlined />;
      default:
        return <QuestionCircleOutlined />;
    }
  };

  // 獲取問題類型標籤顏色
  const getQuestionTypeColor = (type: string) => {
    switch (type) {
      case 'cross_category':
        return 'purple';
      case 'time_based':
        return 'orange';
      case 'category':
        return 'blue';
      default:
        return 'default';
    }
  };

  // 格式化時間
  const formatTime = (dateString?: string) => {
    if (!dateString) return '從未使用';
    
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return '剛剛';
    if (diffMins < 60) return `${diffMins} 分鐘前`;
    if (diffHours < 24) return `${diffHours} 小時前`;
    if (diffDays < 7) return `${diffDays} 天前`;
    return date.toLocaleDateString('zh-TW');
  };

  useEffect(() => {
    loadQuestions();
  }, []);

  useEffect(() => {
    filterQuestions(questions, activeTab, searchText);
  }, [activeTab, searchText, questions]);

  // 分頁效果
  useEffect(() => {
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = startIndex + pageSize;
    setPaginatedQuestions(filteredQuestions.slice(startIndex, endIndex));
  }, [filteredQuestions, currentPage]);

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    setCurrentPage(1); // 切換標籤時重置頁碼
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
    setCurrentPage(1); // 搜索時重置頁碼
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    // 滾動到頂部
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="mobile-question-bank">
      <MobileHeader 
        title="問題銀行" 
        showBack={true}
        onBack={() => navigate(-1)}
      />

      <div className="question-bank-container">
        {/* 統計卡片 */}
        <div className="stats-card">
          <div className="stat-item">
            <div className="stat-value">{stats.total}</div>
            <div className="stat-label">總問題數</div>
          </div>
          <div className="stat-item">
            <div className="stat-value" style={{ color: '#29bf12' }}>{stats.unused}</div>
            <div className="stat-label">未使用</div>
          </div>
          <div className="stat-item">
            <div className="stat-value" style={{ color: '#999' }}>{stats.used}</div>
            <div className="stat-label">已使用</div>
          </div>
        </div>

        {/* 搜索框和刷新按鈕 */}
        <div className="search-bar">
          <Input
            placeholder="搜索問題..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={handleSearchChange}
            style={{ flex: 1 }}
          />
          <Button
            icon={<ReloadOutlined spin={refreshing} />}
            onClick={handleRefresh}
            disabled={refreshing}
            type="primary"
            style={{ marginLeft: '8px' }}
          >
            刷新
          </Button>
        </div>

        {/* 標籤頁 */}
        <div>
          {Object.keys(stats.categories).length > 0 && (
            <div style={{
              fontSize: '11px',
              color: '#999',
              marginBottom: '8px',
              textAlign: 'right',
              padding: '0 4px'
            }}>
              👉 左右滑動查看更多分類
            </div>
          )}
          <Tabs 
            activeKey={activeTab} 
            onChange={handleTabChange}
            className="question-tabs"
          >
            <TabPane tab={`全部 (${stats.total})`} key="all" />
            <TabPane tab={`未使用 (${stats.unused})`} key="unused" />
            <TabPane tab={`已使用 (${stats.used})`} key="used" />
            
            {/* 動態生成聚類分類標籤頁 */}
            {Object.keys(stats.categories).length > 0 && (
              <>
                {Object.entries(stats.categories)
                  .sort((a, b) => b[1] - a[1]) // 按問題數量排序
                  .map(([categoryName, count]) => (
                    <TabPane 
                      tab={
                        <span>
                          <FolderOutlined style={{ marginRight: '4px' }} />
                          {categoryName} ({count})
                        </span>
                      } 
                      key={`category_${categoryName}`} 
                    />
                  ))
                }
              </>
            )}
          </Tabs>
        </div>

        {/* 問題列表 */}
        <div className="questions-list">
          {loading ? (
            <div className="loading-container">
              <Spin size="large" tip="載入中..." />
            </div>
          ) : filteredQuestions.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                questions.length === 0 
                  ? "尚無建議問題，請先生成問題"
                  : "沒有符合條件的問題"
              }
            >
              {questions.length === 0 && (
                <Button 
                  type="primary" 
                  icon={<ThunderboltOutlined />}
                  onClick={handleRefresh}
                  loading={refreshing}
                >
                  立即生成
                </Button>
              )}
            </Empty>
          ) : (
            <>
              {paginatedQuestions.map((question) => (
                <div
                  key={question.id}
                  className="question-item"
                  onClick={() => handleQuestionClick(question)}
                >
                  <div className="question-header">
                    <div className="question-type-icon">
                      {getQuestionTypeIcon(question.is_cross_category ? 'cross_category' : 'category')}
                    </div>
                    <div className="question-content">
                      <div className="question-text">{question.question}</div>
                      <div className="question-meta">
                        {question.category && (
                          <Tag color="blue" style={{ fontSize: '11px' }}>
                            <FolderOutlined style={{ marginRight: '4px' }} />
                            {question.category}
                          </Tag>
                        )}
                        {question.is_cross_category && (
                          <Tag color="purple" style={{ fontSize: '11px' }}>
                            <GlobalOutlined style={{ marginRight: '4px' }} />
                            跨分類
                          </Tag>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="question-footer">
                    <span className="use-info">
                      {question.use_count > 0 ? (
                        <>
                          <CheckCircleOutlined style={{ color: '#999', marginRight: '4px' }} />
                          已使用 {question.use_count} 次
                        </>
                      ) : (
                        <>
                          <Badge status="success" />
                          未使用
                        </>
                      )}
                    </span>
                    <span className="time-info">
                      <ClockCircleOutlined style={{ marginRight: '4px' }} />
                      {formatTime(question.last_used_at)}
                    </span>
                  </div>
                </div>
              ))}
              
              {/* 分頁控件 */}
              {filteredQuestions.length > pageSize && (
                <div style={{ 
                  padding: '20px', 
                  display: 'flex', 
                  justifyContent: 'center',
                  background: 'white',
                  borderRadius: '8px',
                  marginTop: '16px'
                }}>
                  <Pagination
                    current={currentPage}
                    total={filteredQuestions.length}
                    pageSize={pageSize}
                    onChange={handlePageChange}
                    showSizeChanger={false}
                    showQuickJumper={false}
                    showTotal={(total, range) => `${range[0]}-${range[1]} / ${total} 個問題`}
                    simple
                    style={{ fontSize: '14px' }}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default MobileQuestionBank;

