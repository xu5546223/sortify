import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { LogEntry, LogLevel } from '../types/apiTypes';
import { getLogs } from '../services/logService';

interface LogsPageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

interface LogStats {
  total: number;
  errors: number;
  warnings: number;
  info: number;
  debug: number;
}

// 防抖函數
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}

// 新增時間格式化函數
const formatTimestamp = (timestamp: string): string => {
  if (!timestamp) return 'Invalid Date';
  
  try {
    // 解析 ISO 8601 時間格式
    const date = new Date(timestamp);
    
    // 檢查日期是否有效
    if (isNaN(date.getTime())) return 'Invalid Date';
    
    // 格式化為 YYYY-MM-DD HH:MM:SS 格式
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return 'Date Error';
  }
};

const LogsPage: React.FC<LogsPageProps> = ({ showPCMessage }) => {
  const [allLogs, setAllLogs] = useState<LogEntry[]>([]); // 存儲當前過濾的日誌
  const [stats, setStats] = useState<LogStats>({ total: 0, errors: 0, warnings: 0, info: 0, debug: 0 });
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [filterLevel, setFilterLevel] = useState<LogLevel | 'all'>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'timestamp', direction: 'desc' });
  
  const debouncedSearchTerm = useDebounce(searchTerm, 500);
  const isMounted = useRef(true);
  const hasLoadedInitialData = useRef(false);
  
  const LOGS_PER_PAGE = 10;

  // 獲取統計數據（分別獲取各等級）
  const fetchStats = useCallback(async () => {
    try {
      const [allData, errorData, warningData, infoData, debugData] = await Promise.all([
        getLogs('all', '', 'timestamp', 'desc'),
        getLogs('ERROR', '', 'timestamp', 'desc'),
        getLogs('WARNING', '', 'timestamp', 'desc'),
        getLogs('INFO', '', 'timestamp', 'desc'),
        getLogs('DEBUG', '', 'timestamp', 'desc'),
      ]);
      
      if (isMounted.current) {
        setStats({
          total: allData.length,
          errors: errorData.length,
          warnings: warningData.length,
          info: infoData.length,
          debug: debugData.length,
        });
      }
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  }, []);

  // 使用後端過濾獲取日誌
  const fetchLogs = useCallback(async () => {
    if (!isMounted.current) return;
    
    setIsLoading(true);
    try {
      // 使用 filterLevel 進行後端過濾
      const data = await getLogs(
        filterLevel, 
        debouncedSearchTerm, 
        sortConfig.key as keyof LogEntry, 
        sortConfig.direction
      );
      
      if (isMounted.current) {
        setAllLogs(data);
        hasLoadedInitialData.current = true;
      }
    } catch (error) {
      console.error('Failed to fetch logs:', error);
      if (isMounted.current) {
        showPCMessage('獲取日誌失敗', 'error');
        setAllLogs([]);
      }
    }
    
    if (isMounted.current) {
      setIsLoading(false);
    }
  }, [filterLevel, debouncedSearchTerm, sortConfig, showPCMessage]);

  useEffect(() => {
    isMounted.current = true;
    fetchLogs();
    fetchStats();
    return () => {
      isMounted.current = false;
    };
  }, [fetchLogs]);

  // 現在日誌已經由後端過濾，直接使用 allLogs
  const filteredLogs = allLogs;

  // 分頁計算
  const totalPages = Math.ceil(filteredLogs.length / LOGS_PER_PAGE);
  const startIndex = (currentPage - 1) * LOGS_PER_PAGE;
  const endIndex = startIndex + LOGS_PER_PAGE;
  const paginatedLogs = filteredLogs.slice(startIndex, endIndex);

  // 當過濾條件改變時重置到第一頁
  useEffect(() => {
    setCurrentPage(1);
  }, [filterLevel, debouncedSearchTerm]);

  // 獲取日誌等級的 Badge 樣式
  const getLogBadgeClass = (level: LogLevel): string => {
    switch (level) {
      case 'ERROR':
        return 'bg-error text-white border-2 border-[var(--color-border)] font-bold';
      case 'WARNING':
        return 'bg-warn text-black border-2 border-[var(--color-border)] font-bold';
      case 'INFO':
        return 'bg-active text-white border-2 border-[var(--color-border)] font-bold';
      case 'DEBUG':
        return 'bg-card text-[var(--color-text-sub)] border-2 border-[var(--color-border)] font-bold';
      default:
        return 'bg-card text-[var(--color-text-sub)] border-2 border-[var(--color-border)] font-bold';
    }
  };

  // 複製文字到剪貼簿
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      showPCMessage('已複製到剪貼簿', 'success');
    }).catch(() => {
      showPCMessage('複製失敗', 'error');
    });
  };

  const handleDownloadLogs = () => {
    if (filteredLogs.length === 0) {
      showPCMessage('目前沒有日誌可供下載', 'info');
      return;
    }

    try {
      // CSV 轉義函數：處理包含逗號、引號和換行的內容
      const escapeCsvValue = (value: string) => {
        if (!value) return '""';
        // 如果包含逗號、引號或換行，需要用引號包裹並轉義內部引號
        if (value.includes(',') || value.includes('"') || value.includes('\n')) {
          return `"${value.replace(/"/g, '""')}"`;
        }
        return `"${value}"`;
      };
      
      // CSV 標頭
      const headers = 'Timestamp,Level,Message,Source\n';
      
      // CSV 內容
      const csvContent = headers + filteredLogs.map(log => {
        const timestamp = formatTimestamp(log.timestamp);
        const level = log.level;
        const message = log.message || '';
        const source = log.source || 'N/A';
        
        return [timestamp, level, message, source]
          .map(escapeCsvValue)
          .join(',');
      }).join('\n');

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      
      const date = new Date().toISOString().split('T')[0];
      link.setAttribute('href', url);
      link.setAttribute('download', `sortify_logs_${date}.csv`);
      
      document.body.appendChild(link);
      link.click();
      
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      showPCMessage('日誌下載成功（CSV）', 'success');
    } catch (error) {
      console.error('下載日誌時發生錯誤:', error);
      showPCMessage('下載日誌時發生錯誤', 'error');
    }
  };

  const refreshLogs = () => {
    fetchLogs();
    fetchStats();
  };

  return (
    <div className="bg-bg p-6 md:p-10 transition-colors duration-300">
      {/* Header & Stats */}
      <header className="flex flex-col gap-6 mb-6 flex-shrink-0">
        <div className="flex justify-between items-end flex-wrap gap-4">
          <div>
            <h1 className="font-heading text-4xl font-black mb-1 uppercase">SYSTEM LOGS</h1>
            <p className="font-bold text-[var(--color-text-sub)]">監控系統事件、錯誤和除錯資訊</p>
          </div>
          <button 
            onClick={handleDownloadLogs}
            className="neo-btn-primary px-6 py-3 text-sm"
          >
            <i className="fas fa-download mr-2"></i> Export CSV
          </button>
        </div>

        {/* 1. 數據概覽卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Total */}
          <div className="neo-card p-4 flex items-center justify-between">
            <div>
              <div className="text-xs font-black text-[var(--color-text-sub)] uppercase tracking-wider">Total Logs (24h)</div>
              <div className="text-3xl font-heading font-black mt-1">{stats.total}</div>
            </div>
            <i className="fas fa-scroll text-4xl opacity-20"></i>
          </div>

          {/* Errors (Highlight) */}
          <div className="neo-card p-4 flex items-center justify-between bg-error text-white relative overflow-hidden">
            <div className="relative z-10">
              <div className="text-xs font-black opacity-80 uppercase tracking-wider">Errors</div>
              <div className="text-3xl font-heading font-black mt-1">{stats.errors}</div>
            </div>
            <i className="fas fa-exclamation-triangle text-5xl text-black opacity-20 absolute -right-2 -bottom-2"></i>
          </div>

          {/* Warnings */}
          <div className="neo-card p-4 flex items-center justify-between bg-warn text-black">
            <div>
              <div className="text-xs font-black opacity-70 uppercase tracking-wider">Warnings</div>
              <div className="text-3xl font-heading font-black mt-1">{stats.warnings}</div>
            </div>
            <i className="fas fa-exclamation-circle text-4xl opacity-20"></i>
          </div>

          {/* Status */}
          <div className="neo-card p-4 flex items-center gap-3 bg-[var(--color-text)] text-[var(--color-hover)]">
            <div className="w-3 h-3 bg-[var(--color-hover)] rounded-full animate-pulse"></div>
            <div>
              <div className="text-xs font-black opacity-80 uppercase tracking-wider">System Status</div>
              <div className="text-xl font-heading font-black mt-0.5">OPERATIONAL</div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="neo-card p-0 mb-6">
        {/* 2. 控制工具列 */}
        <div className="p-4 border-b-[3px] border-[var(--color-border)] bg-bg flex flex-col md:flex-row gap-4 items-center justify-between">
          {/* 快速篩選 Chips */}
          <div className="flex gap-2 overflow-x-auto w-full md:w-auto pb-1 md:pb-0">
            <button
              onClick={() => setFilterLevel('all')}
              className={`px-4 py-2 border-2 border-[var(--color-border)] font-black text-sm uppercase transition-all ${
                filterLevel === 'all'
                  ? 'bg-[var(--color-text)] text-[var(--color-card)] shadow-[3px_3px_0px_0px_var(--color-active)]'
                  : 'bg-card hover:bg-hover'
              }`}
            >
              ALL LEVELS
            </button>
            <button
              onClick={() => setFilterLevel('ERROR')}
              className={`px-4 py-2 border-2 border-[var(--color-border)] font-black text-sm uppercase transition-all ${
                filterLevel === 'ERROR'
                  ? 'bg-[var(--color-text)] text-[var(--color-card)]'
                  : 'bg-card text-error hover:bg-red-50'
              }`}
            >
              ERROR ({stats.errors})
            </button>
            <button
              onClick={() => setFilterLevel('WARNING')}
              className={`px-4 py-2 border-2 border-[var(--color-border)] font-black text-sm uppercase transition-all ${
                filterLevel === 'WARNING'
                  ? 'bg-[var(--color-text)] text-[var(--color-card)]'
                  : 'bg-card text-warn hover:bg-orange-50'
              }`}
            >
              WARN ({stats.warnings})
            </button>
            <button
              onClick={() => setFilterLevel('INFO')}
              className={`px-4 py-2 border-2 border-[var(--color-border)] font-black text-sm uppercase transition-all ${
                filterLevel === 'INFO'
                  ? 'bg-[var(--color-text)] text-[var(--color-card)]'
                  : 'bg-card text-active hover:bg-blue-50'
              }`}
            >
              INFO ({stats.info})
            </button>
            <button
              onClick={() => setFilterLevel('DEBUG')}
              className={`px-4 py-2 border-2 border-[var(--color-border)] font-black text-sm uppercase transition-all ${
                filterLevel === 'DEBUG'
                  ? 'bg-[var(--color-text)] text-[var(--color-card)]'
                  : 'bg-card text-[var(--color-text-sub)] hover:bg-gray-100'
              }`}
            >
              DEBUG ({stats.debug})
            </button>
          </div>

          {/* 搜尋與刷新 */}
          <div className="flex gap-3 w-full md:w-auto">
            <div className="relative flex-1 md:w-80">
              <i className="fas fa-search absolute left-3 top-1/2 transform -translate-y-1/2 text-[var(--color-text-sub)]"></i>
              <input
                type="text"
                placeholder="Search messages or trace ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="neo-input pl-10 py-2 text-sm w-full"
              />
            </div>
            <button
              onClick={refreshLogs}
              className="neo-btn-primary w-10 h-10 flex items-center justify-center p-0"
              title="Refresh"
            >
              <i className="fas fa-sync-alt text-xl"></i>
            </button>
          </div>
        </div>

        {/* 3. 日誌表格 */}
        <div className="bg-card relative">
          {isLoading && allLogs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 opacity-50">
              <i className="fas fa-spinner fa-spin text-4xl mb-2"></i>
              <span className="font-black font-mono">LOADING_LOGS...</span>
            </div>
          ) : paginatedLogs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 opacity-50">
              <i className="fas fa-inbox text-4xl mb-2"></i>
              <span className="font-black font-mono">NO_LOGS_FOUND</span>
            </div>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 bg-card z-10 shadow-sm">
                <tr className="border-b-[3px] border-[var(--color-border)] uppercase text-xs font-black text-[var(--color-text-sub)] tracking-wider">
                  <th className="p-4 w-48 bg-bg border-r-2 border-[var(--color-border)]">Timestamp</th>
                  <th className="p-4 w-32 bg-bg border-r-2 border-[var(--color-border)] text-center">Level</th>
                  <th className="p-4 bg-bg border-r-2 border-[var(--color-border)]">Message</th>
                  <th className="p-4 w-64 bg-bg">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y-2 divide-[var(--color-border)] text-sm font-bold">
                {paginatedLogs.map((log) => (
                  <tr
                    key={log.id}
                    className={`hover:bg-hover hover:bg-opacity-20 transition-colors group ${
                      log.level === 'ERROR' ? 'bg-red-50' : ''
                    }`}
                  >
                    {/* Timestamp */}
                    <td className="p-4 font-mono text-xs border-r-2 border-[var(--color-border)] border-dashed">
                      {formatTimestamp(log.timestamp).split(' ')[0]}<br />
                      <span className="text-[var(--color-text-sub)]">{formatTimestamp(log.timestamp).split(' ')[1]}</span>
                    </td>

                    {/* Level Badge */}
                    <td className="p-4 text-center border-r-2 border-[var(--color-border)] border-dashed">
                      <span className={`px-2 py-1 text-xs uppercase ${getLogBadgeClass(log.level)} inline-block min-w-[80px] text-center`}>
                        {log.level}
                      </span>
                    </td>

                    {/* Message */}
                    <td className="p-4 border-r-2 border-[var(--color-border)] border-dashed relative">
                      <div className={`font-mono ${
                        log.level === 'ERROR' ? 'text-error' : 'text-[var(--color-text)]'
                      }`}>
                        {log.message}
                      </div>
                    </td>

                    {/* Source */}
                    <td className="p-4 font-mono text-xs text-[var(--color-text-sub)]">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate" title={log.source || 'N/A'}>
                          {log.source || 'N/A'}
                        </span>
                        <button
                          onClick={() => {
                            const logText = `[${formatTimestamp(log.timestamp)}] [${log.level}] ${log.message}\nSource: ${log.source || 'N/A'}`;
                            copyToClipboard(logText);
                          }}
                          className="opacity-0 group-hover:opacity-100 hover:text-active transition-all"
                          title="Copy Log Entry"
                        >
                          <i className="fas fa-copy"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* 4. 分頁控制 */}
        <div className="p-4 bg-bg border-t-[3px] border-[var(--color-border)] flex justify-between items-center">
          <div className="text-xs font-black text-[var(--color-text-sub)]">
            Showing {startIndex + 1}-{Math.min(endIndex, filteredLogs.length)} of {filteredLogs.length} {filterLevel !== 'all' && `(${stats.total} total)`}
          </div>
          
          {totalPages > 1 && (
            <div className="flex gap-2 items-center">
              <button
                onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
                className="neo-btn-primary w-8 h-8 flex items-center justify-center p-0 disabled:opacity-50 disabled:cursor-not-allowed"
                title="Previous"
              >
                <i className="fas fa-caret-left"></i>
              </button>
              
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum: number;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else if (currentPage <= 3) {
                  pageNum = i + 1;
                } else if (currentPage >= totalPages - 2) {
                  pageNum = totalPages - 4 + i;
                } else {
                  pageNum = currentPage - 2 + i;
                }
                
                return (
                  <button
                    key={pageNum}
                    onClick={() => setCurrentPage(pageNum)}
                    className={`px-3 py-1 border-2 border-[var(--color-border)] font-black text-xs uppercase transition-all ${
                      currentPage === pageNum
                        ? 'bg-[var(--color-text)] text-[var(--color-card)]'
                        : 'bg-card hover:bg-hover'
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}
              
              {totalPages > 5 && currentPage < totalPages - 2 && (
                <span className="font-black text-[var(--color-text-sub)]">...</span>
              )}
              
              <button
                onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
                className="neo-btn-primary w-8 h-8 flex items-center justify-center p-0 disabled:opacity-50 disabled:cursor-not-allowed"
                title="Next"
              >
                <i className="fas fa-caret-right"></i>
              </button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default LogsPage;