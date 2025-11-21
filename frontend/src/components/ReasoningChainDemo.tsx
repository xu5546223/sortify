/**
 * Reasoning Chain Demo Component
 * 用於測試和預覽推理鏈效果
 * 
 * 功能：
 * - ✅ 推理鏈展示（Thought → Action → Observation → Approval）
 * - ✅ Human-in-the-loop 批准卡片
 * - ✅ Streamdown 流式 Markdown 渲染
 * - ✅ 可點擊的引用標籤（後處理方式，參考 vercel/streamdown#23）
 * - ✅ 側邊文檔預覽面板
 */
import React, { useState, useEffect, useMemo } from 'react';
import ReasoningChainDisplay, { ReasoningStep } from './ReasoningChainDisplay';
import { Button, Space, Drawer } from 'antd';
import { Streamdown } from 'streamdown';
import './ReasoningChainDemo.css';

// 模擬文檔數據
const mockDocuments = [
  {
    id: 1,
    title: 'Contract_v2.pdf',
    page: 4,
    content: '3.1 付款條款：本合約簽署後十日內，甲方應支付乙方總價金之30%作為預付款。\n\n3.2 第一階段里程碑驗收完成後，支付40%。',
    highlight: '3.1 付款條款：本合約簽署後十日內，甲方應支付乙方總價金之30%作為預付款。'
  },
  {
    id: 2,
    title: 'Penalty_Rules.docx',
    page: 1,
    content: '延遲罰則：每逾期一日，罰款總額 0.1%。',
    highlight: '每逾期一日，罰款總額 0.1%'
  }
];

const ReasoningChainDemo: React.FC = () => {
  const [steps, setSteps] = useState<ReasoningStep[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<typeof mockDocuments[0] | null>(null);
  const [showApproval, setShowApproval] = useState(false);
  const [approvalGranted, setApprovalGranted] = useState(false);

  // 處理引用點擊
  const handleCitationClick = (docId: number) => {
    const doc = mockDocuments.find(d => d.id === docId);
    if (doc) {
      setSelectedDoc(doc);
      setPreviewOpen(true);
    }
  };

  // 預處理：將引用標記轉換為特殊占位符
  const preprocessCitations = (text: string): string => {
    // 將 [文本](citation:數字) 替換為 {{CITATION:數字:文本}}
    return text.replace(
      /\[([^\]]+)\]\(citation:(\d+)\)/g,
      '{{CITATION:$2:$1}}'
    );
  };

  // 後處理：將占位符轉換為可點擊的標籤
  const processTextWithCitations = (text: string): (string | JSX.Element)[] => {
    if (!text) return [text];
    
    // 匹配 {{CITATION:數字:文本}}
    const parts = text.split(/({{CITATION:\d+:[^}]+}})/g);
    const result: (string | JSX.Element)[] = [];
    
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const citationMatch = part.match(/{{CITATION:(\d+):([^}]+)}}/);
      
      if (citationMatch) {
        const docId = parseInt(citationMatch[1]);
        const citationText = citationMatch[2];
        
        result.push(
          <span
            key={`citation-${i}-${docId}`}
            className="demo-citation"
            onClick={() => handleCitationClick(docId)}
          >
            <i className={docId === 1 ? 'ph-fill ph-file-pdf' : 'ph-fill ph-file-text'}></i>
            {citationText}
          </span>
        );
      } else if (part) {
        result.push(part);
      }
    }
    
    return result.filter(p => p !== undefined && p !== '');
  };

  // 自定義 Streamdown 組件（後處理引用標籤）
  const customStreamdownComponents = useMemo(
    () => ({
      p: ({ children, ...props }: any) => {
        if (typeof children === 'string') {
          const processedContent = processTextWithCitations(children);
          return <p {...props} style={{ marginBottom: '16px', lineHeight: '1.6' }}>{processedContent}</p>;
        }
        
        const processedChildren = Array.isArray(children)
          ? children.map((child: any, index: number) => {
              if (typeof child === 'string') {
                return processTextWithCitations(child);
              }
              return child;
            }).flat()
          : children;
        
        return <p {...props} style={{ marginBottom: '16px', lineHeight: '1.6' }}>{processedChildren}</p>;
      },
      strong: ({ children }: any) => (
        <strong style={{ fontWeight: 600, color: '#000' }}>{children}</strong>
      )
    }),
    []
  );

  // 模擬流式添加步驟
  const simulateStreaming = () => {
    setSteps([]);
    setIsStreaming(true);
    setShowAnswer(false);
    setStreamingText('');

    const demoSteps: ReasoningStep[] = [
      {
        type: 'thought',
        stage: 'classification',
        message: '分析用戶意圖：搜索特定專案合約 + 提取條款',
        status: 'done',
        timestamp: Date.now()
      },
      {
        type: 'action',
        stage: 'tool_call',
        message: '調用工具: vector_search',
        detail: {
          tool: 'vector_search',
          params: {
            query: '新竹科學園區專案 合約',
            filter: { type: 'contract' },
            top_k: 3
          }
        },
        status: 'done',
        timestamp: Date.now() + 1000
      },
      {
        type: 'observation',
        stage: 'search_result',
        message: '找到 3 個相關文檔，相關度最高 0.92',
        status: 'done',
        timestamp: Date.now() + 2000
      },
      {
        type: 'approval',
        stage: 'approval_needed',
        message: '需要權限批准',
        detail: {
          message: '搜尋結果包含一份標記為機密的文件',
          files: ['2024_Hsinchu_Project_NDA_Signed.pdf']
        },
        status: 'active',
        timestamp: Date.now() + 3000
      }
    ];

    // 逐步添加步驟
    demoSteps.forEach((step, index) => {
      setTimeout(() => {
        setSteps(prev => [...prev, step]);
        
        // 第4步顯示批准卡片
        if (index === 3) {
          setTimeout(() => {
            setShowApproval(true);
          }, 500);
        }
      }, index * 800);
    });
  };

  // 模擬文字流式生成
  const simulateTextStreaming = () => {
    const fullText = `根據檢索到的 [主合約文檔](citation:1)，關於新竹科學園區專案的付款條款總結如下：

**預付款：** 簽約後 10 日內支付總金額的 ==30%==。

**進度款：** 第一階段驗收通過後，支付 40%。

**尾款：** 專案結案後支付剩餘 30%，保留款 5% 於保固期滿後退還。

另外，根據 [附件三：罰則](citation:2)，若延遲交付，每日罰款為合約總額的 **0.1%**。

---

### 快速操作
- 📄 生成 PDF 報告
- 📧 寄給財務部`;
    
    let index = 0;
    const interval = setInterval(() => {
      if (index < fullText.length) {
        setStreamingText(fullText.substring(0, index + 1));
        index++;
      } else {
        clearInterval(interval);
        setIsStreaming(false);
        // 更新最後一步狀態為完成
        setSteps(prev => prev.map((s, i) => 
          i === prev.length - 1 ? { ...s, status: 'done' as const, message: '答案生成完成' } : s
        ));
      }
    }, 20); // 加快速度到 20ms
  };

  // 處理批准
  const handleApprove = () => {
    setApprovalGranted(true);
    setShowApproval(false);
    
    // 更新批准步驟狀態
    setSteps(prev => prev.map((s, i) => 
      i === prev.length - 1 ? { ...s, status: 'done' as const } : s
    ));
    
    // 添加生成步驟
    setTimeout(() => {
      setSteps(prev => [...prev, {
        type: 'generating',
        stage: 'answer_generation',
        message: '正在生成答案...',
        status: 'active',
        timestamp: Date.now()
      }]);
      
      setTimeout(() => {
        setShowAnswer(true);
        simulateTextStreaming();
      }, 500);
    }, 500);
  };

  const handleReject = () => {
    setShowApproval(false);
    alert('已拒絕讀取機密文件');
  };

  // 重置
  const reset = () => {
    setSteps([]);
    setIsStreaming(false);
    setShowAnswer(false);
    setStreamingText('');
    setPreviewOpen(false);
    setSelectedDoc(null);
    setShowApproval(false);
    setApprovalGranted(false);
  };

  return (
    <div className="reasoning-demo-container">
      {/* 左側主區域 */}
      <div className="reasoning-demo-main">
        <h1 className="reasoning-demo-title">REASONING CHAIN DEMO</h1>
        
        <Space style={{ marginBottom: '24px' }}>
          <Button 
            type="primary" 
            onClick={simulateStreaming}
            disabled={isStreaming}
            className="demo-btn-primary"
          >
            開始模擬流式輸出
          </Button>
          <Button onClick={reset} className="demo-btn-secondary">
            重置
          </Button>
        </Space>

        {/* 用戶問題氣泡 */}
        {steps.length > 0 && (
          <div className="demo-user-bubble">
            <div className="demo-user-avatar">
              <i className="ph-bold ph-user"></i>
            </div>
            <div className="demo-user-content">
              <p>請幫我查找「新竹科學園區專案」相關的合約，並總結一下付款條款。</p>
            </div>
          </div>
        )}

        {/* AI 回答容器 */}
        {steps.length > 0 && (
          <div className="demo-ai-bubble">
            <div className="demo-ai-avatar">AI</div>
            
            <div className="demo-ai-container">
              {/* 推理鏈 */}
              <ReasoningChainDisplay
                steps={steps}
                isStreaming={isStreaming && !showAnswer}
                processingTime={steps.length > 0 ? (Date.now() - steps[0].timestamp!) / 1000 : undefined}
              />

              {/* 批准卡片 - Human-in-the-loop */}
              {showApproval && (
                <div className="demo-approval-card">
                  <div className="approval-card-indicator"></div>
                  <h4 className="approval-card-title">
                    <i className="ph-fill ph-lock-key"></i>
                    需要權限批准
                  </h4>
                  <p className="approval-card-message">
                    搜尋結果包含一份標記為 <strong>機密 (Confidential)</strong> 的文件：
                  </p>
                  <div className="approval-card-files">
                    <span className="approval-file-badge">
                      <i className="ph-fill ph-file-pdf"></i>
                      2024_Hsinchu_Project_NDA_Signed.pdf
                    </span>
                  </div>
                  <div className="approval-card-actions">
                    <button 
                      className="approval-btn-approve"
                      onClick={handleApprove}
                    >
                      <i className="ph-bold ph-check"></i>
                      允許讀取
                    </button>
                    <button 
                      className="approval-btn-reject"
                      onClick={handleReject}
                    >
                      <i className="ph-bold ph-x"></i>
                      跳過此文件
                    </button>
                  </div>
                </div>
              )}

              {/* 生成的答案 - 使用 Streamdown 流式渲染 */}
              {showAnswer && (
                <div className="demo-answer-content">
                  <div className="demo-answer-label">
                    <i className="ph-bold ph-text-t"></i>
                    <span>{isStreaming ? 'GENERATING RESPONSE...' : 'RESPONSE COMPLETE'}</span>
                  </div>
                  
                  <div className="demo-answer-text">
                    {/* 使用 Streamdown 進行流式 Markdown 渲染 */}
                    {/* 預處理：將 [文本](citation:1) 轉為 {{CITATION:1:文本}} */}
                    <Streamdown
                      components={customStreamdownComponents}
                    >
                      {preprocessCitations(streamingText)}
                    </Streamdown>
                    
                    {/* 流式游標 */}
                    {isStreaming && <span className="demo-cursor">▋</span>}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 空狀態 */}
        {steps.length === 0 && (
          <div className="demo-empty-state">
            <i className="ph-bold ph-chat-circle-dots" style={{ fontSize: '48px', color: '#d1d5db', marginBottom: '16px' }}></i>
            <p style={{ color: '#9ca3af', marginBottom: '16px' }}>
              點擊「開始模擬流式輸出」查看完整效果
            </p>
            <p style={{ fontSize: '12px', color: '#d1d5db' }}>
              包含推理鏈、文檔引用、側邊預覽等功能
            </p>
          </div>
        )}
      </div>

      {/* 右側預覽面板 */}
      <Drawer
        title={
          <div className="demo-preview-header">
            <div className="demo-preview-indicator"></div>
            <span>SOURCE PREVIEW</span>
          </div>
        }
        placement="right"
        onClose={() => setPreviewOpen(false)}
        open={previewOpen}
        width={400}
        className="demo-preview-drawer"
      >
        {selectedDoc && (
          <div className="demo-preview-content">
            <div className="demo-preview-doc-card">
              <div className="demo-preview-doc-header">
                <i className="ph-fill ph-file-pdf"></i>
                <span>{selectedDoc.title}</span>
                <span className="demo-preview-page">Pg. {selectedDoc.page}</span>
              </div>
              
              <div className="demo-preview-doc-content">
                <div className="demo-preview-context-label">...context match...</div>
                <div className="demo-preview-highlight">
                  {selectedDoc.highlight}
                </div>
                <div className="demo-preview-text">
                  {selectedDoc.content.replace(selectedDoc.highlight, '')}
                </div>
              </div>
              
              <div className="demo-preview-doc-footer">
                <button className="demo-preview-open-btn">
                  Open File <i className="ph-bold ph-arrow-square-out"></i>
                </button>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default ReasoningChainDemo;
