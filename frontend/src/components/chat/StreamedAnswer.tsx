/**
 * StreamedAnswer Component
 * 
 * 流式答案渲染組件，使用 Streamdown 進行高性能 Markdown 渲染
 * 支持引用標籤點擊和流式游標顯示
 */
import React, { useMemo } from 'react';
import { Streamdown } from 'streamdown';
import './StreamedAnswer.css';

export interface StreamedAnswerProps {
  content: string;
  isStreaming?: boolean;
  onCitationClick?: (docId: number) => void;
}

const StreamedAnswer: React.FC<StreamedAnswerProps> = ({
  content,
  isStreaming = false,
  onCitationClick
}) => {
  // 預處理：將引用標記轉換為特殊占位符（避免 Streamdown 阻擋 citation: URL）
  const preprocessCitations = (text: string): string => {
    // 1. 將 [文本](citation:數字) 替換為 {{CITATION:數字:文本}}
    let processed = text.replace(
      /\[([^\]]+)\]\(citation:(\d+)\)/g,
      '{{CITATION:$2:$1}}'
    );

    // 2. 將所有 CITATION 標籤強制包裹在反引號中，轉變為行內代碼塊
    // 這樣可以利用 Markdown 的特性，保護內容（特別是文件名中的下劃線）不被解析為斜體
    processed = processed.replace(/{{CITATION:(\d+):([^}]+)}}/g, '`{{CITATION:$1:$2}}`');

    // 3. 清理可能產生的雙重反引號（如果原文已經包含反引號）
    processed = processed.replace(/``{{CITATION/g, '`{{CITATION');
    processed = processed.replace(/}}``/g, '}}`');

    return processed;
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
            className="citation-tag"
            onClick={() => onCitationClick?.(docId)}
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
      strong: ({ children }: any) => {
        // ✅ 处理 strong 标签中的引用
        if (typeof children === 'string') {
          const processedContent = processTextWithCitations(children);
          return <strong style={{ fontWeight: 600, color: '#000' }}>{processedContent}</strong>;
        }
        
        const processedChildren = Array.isArray(children)
          ? children.map((child: any, index: number) => {
              if (typeof child === 'string') {
                return processTextWithCitations(child);
              }
              return child;
            }).flat()
          : children;
        
        return <strong style={{ fontWeight: 600, color: '#000' }}>{processedChildren}</strong>;
      },
      em: ({ children }: any) => {
        // ✅ 处理 em 标签中的引用
        if (typeof children === 'string') {
          const processedContent = processTextWithCitations(children);
          return <em>{processedContent}</em>;
        }
        
        const processedChildren = Array.isArray(children)
          ? children.map((child: any, index: number) => {
              if (typeof child === 'string') {
                return processTextWithCitations(child);
              }
              return child;
            }).flat()
          : children;
        
        return <em>{processedChildren}</em>;
      },
      ul: ({ children }: any) => (
        <ul style={{ marginBottom: '16px', paddingLeft: '24px' }}>{children}</ul>
      ),
      ol: ({ children }: any) => (
        <ol style={{ marginBottom: '16px', paddingLeft: '24px' }}>{children}</ol>
      ),
      li: ({ children }: any) => {
        // ✅ 处理列表项中的引用
        if (typeof children === 'string') {
          const processedContent = processTextWithCitations(children);
          return <li style={{ marginBottom: '8px' }}>{processedContent}</li>;
        }
        
        const processedChildren = Array.isArray(children)
          ? children.map((child: any, index: number) => {
              if (typeof child === 'string') {
                return processTextWithCitations(child);
              }
              return child;
            }).flat()
          : children;
        
        return <li style={{ marginBottom: '8px' }}>{processedChildren}</li>;
      },
      // 添加通用文本处理器（捕获所有纯文本节点）
      text: ({ children }: any) => {
        if (typeof children === 'string') {
          const processed = processTextWithCitations(children);
          // 如果处理后是数组（包含引用元素），返回 Fragment
          if (Array.isArray(processed)) {
            return <>{processed}</>;
          }
          return processed;
        }
        return children;
      },
      // 攔截代碼塊，如果是引用格式則渲染為按鈕
      code: ({ inline, className, children, ...props }: any) => {
        const content = String(children);
        // 檢查是否包含 CITATION 標籤
        const match = content.match(/{{CITATION:(\d+):([^}]+)}}/);
        if (match) {
          // 使用 processTextWithCitations 處理（它會返回包含按鈕的數組）
          // 注意：我們只處理匹配到的部分，如果代碼塊裡還有其他內容，這裡做簡化處理：
          // 假設預處理步驟已經將每個 CITATION 單獨包裹在代碼塊中
          const processed = processTextWithCitations(match[0]);
          if (Array.isArray(processed)) {
            return <>{processed}</>;
          }
          return processed;
        }
        return <code className={className} {...props}>{children}</code>;
      },
      // 添加 div 和 span 處理器
      div: ({ children, ...props }: any) => {
        if (typeof children === 'string') {
          const processedContent = processTextWithCitations(children);
          return <div {...props}>{processedContent}</div>;
        }
        
        const processedChildren = Array.isArray(children)
          ? children.map((child: any, index: number) => {
              if (typeof child === 'string') {
                return processTextWithCitations(child);
              }
              return child;
            }).flat()
          : children;
        
        return <div {...props}>{processedChildren}</div>;
      },
      span: ({ children, ...props }: any) => {
        if (typeof children === 'string') {
          const processedContent = processTextWithCitations(children);
          return <span {...props}>{processedContent}</span>;
        }
        return <span {...props}>{children}</span>;
      }
    }),
    [onCitationClick]
  );

  // ✅ 渲染 Streamdown 内容，然后处理所有剩余的引用占位符
  const renderContent = () => {
    const preprocessedContent = preprocessCitations(content);
    
    // 如果内容很简单（没有 Markdown），直接处理引用
    if (!preprocessedContent.includes('\n') && !preprocessedContent.includes('**')) {
      const processed = processTextWithCitations(preprocessedContent);
      return <div style={{ marginBottom: '16px', lineHeight: '1.6' }}>{processed}</div>;
    }
    
    // 否则使用 Streamdown 渲染 Markdown
    return (
      <Streamdown components={customStreamdownComponents}>
        {preprocessedContent}
      </Streamdown>
    );
  };

  return (
    <div className="streamed-answer-container">
      <div className="streamed-answer-label">
        <i className="ph-bold ph-text-t"></i>
        <span>{isStreaming ? 'GENERATING RESPONSE...' : 'RESPONSE COMPLETE'}</span>
      </div>
      
      <div className="streamed-answer-content">
        {renderContent()}
        
        {/* 流式游標 */}
        {isStreaming && <span className="typing-cursor">▋</span>}
      </div>
    </div>
  );
};

export default StreamedAnswer;
