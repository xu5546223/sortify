import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';

interface DocumentPoolItem {
  document_id: string;
  filename: string;
  [key: string]: any;
}

interface StreamedMarkdownProps {
  content: string;
  isStreaming?: boolean;
  onCitationClick?: (docId: number) => void;
  documentPool?: DocumentPoolItem[];
  onFileClick?: (documentId: string) => void;
}

// 文件擴展名列表
const FILE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'md'];

// 獲取文件圖標
const getFileIcon = (filename: string): string => {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return '🖼️';
  if (ext === 'pdf') return '📕';
  if (['txt', 'md'].includes(ext)) return '📄';
  if (['doc', 'docx'].includes(ext)) return '📘';
  if (['xls', 'xlsx'].includes(ext)) return '📗';
  return '📎';
};

/**
 * 流式 Markdown 渲染組件
 * 
 * 性能優化：
 * 1. 使用 useMemo 緩存渲染結果，只在內容變化時重新渲染
 * 2. 代碼塊使用 Syntax Highlighter 高亮顯示
 * 3. 支持 GitHub Flavored Markdown (GFM)
 * 4. 支持文檔引用點擊 (citation:N)
 * 5. 支持文件名連結點擊（帶圖標按鈕樣式）
 * 
 * 參考 ChatGPT/Gemini 的最佳實踐
 */
export const StreamedMarkdown: React.FC<StreamedMarkdownProps> = ({
  content,
  isStreaming = false,
  onCitationClick,
  documentPool = [],
  onFileClick
}) => {
  // 預處理：將文件名連結轉換為特殊佔位符
  const preprocessContent = (text: string): string => {
    let processed = text;

    // 1. 將 [文本](citation:數字) 替換為 {{CITATION:數字:文本}}
    processed = processed.replace(
      /\[([^\]]+)\]\(citation:(\d+)\)/g,
      '{{CITATION:$2:$1}}'
    );

    // 2. 將文件連結 [文件名](文件名.ext) 替換為 {{FILE:文件名:顯示文本}}
    const fileExtPattern = FILE_EXTENSIONS.join('|');
    const fileRegex = new RegExp(
      `\\[([^\\]]+)\\]\\(([^)]+\\.(?:${fileExtPattern}))\\)`,
      'gi'
    );
    processed = processed.replace(fileRegex, '{{FILE:$2:$1}}');

    return processed;
  };

  // 後處理：將佔位符轉換為可點擊的標籤
  const processTextWithCitations = (text: string): (string | JSX.Element)[] => {
    if (!text || typeof text !== 'string') return [text];

    // 匹配 {{CITATION:數字:文本}} 和 {{FILE:文件名:顯示文本}}
    const parts = text.split(/({{CITATION:\d+:[^}]+}}|{{FILE:[^}]+:[^}]+}})/g);
    const result: (string | JSX.Element)[] = [];

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      if (!part) continue;

      // 處理 CITATION 標籤
      const citationMatch = part.match(/{{CITATION:(\d+):([^}]+)}}/);
      if (citationMatch) {
        const docId = parseInt(citationMatch[1]);
        const citationText = citationMatch[2];

        result.push(
          <span
            key={`citation-${i}-${docId}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              background: '#e6f7ff',
              color: '#1890ff',
              borderRadius: '4px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              border: '1px solid #91d5ff',
              margin: '0 2px'
            }}
            onClick={() => onCitationClick?.(docId)}
          >
            <span>📄</span>
            <span>{citationText}</span>
          </span>
        );
        continue;
      }

      // 處理 FILE 標籤
      const fileMatch = part.match(/{{FILE:([^:]+):([^}]+)}}/);
      if (fileMatch) {
        const filename = fileMatch[1];
        const displayText = fileMatch[2];

        // 從 documentPool 查找文檔
        const matchedDoc = documentPool.find(doc =>
          doc.filename === filename ||
          doc.filename.includes(filename) ||
          filename.includes(doc.filename)
        );

        result.push(
          <span
            key={`file-${i}-${filename}`}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '2px 8px',
              background: '#f0f5ff',
              color: '#1890ff',
              borderRadius: '4px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              border: '1px solid #adc6ff',
              margin: '0 2px'
            }}
            onClick={() => {
              console.log('📄 點擊文件標籤:', filename, matchedDoc);
              if (matchedDoc && onFileClick) {
                onFileClick(matchedDoc.document_id);
              } else if (matchedDoc && onCitationClick) {
                const index = documentPool.findIndex(d => d.document_id === matchedDoc.document_id);
                if (index >= 0) onCitationClick(index + 1);
              }
            }}
          >
            <span>{getFileIcon(filename)}</span>
            <span>{displayText}</span>
          </span>
        );
        continue;
      }

      result.push(part);
    }

    return result.filter(p => p !== undefined && p !== '');
  };

  // 處理 children（可能是字符串或數組）
  const processChildren = (children: any): any => {
    if (typeof children === 'string') {
      return processTextWithCitations(children);
    }
    if (Array.isArray(children)) {
      return children.map((child: any, idx: number) => {
        if (typeof child === 'string') {
          const processed = processTextWithCitations(child);
          return processed.length === 1 ? processed[0] : processed;
        }
        return child;
      }).flat();
    }
    return children;
  };

  // 使用 useMemo 緩存 Markdown 渲染結果
  const renderedContent = useMemo(() => {
    const preprocessedContent = preprocessContent(content);

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 自定義代碼塊渲染
          code({ node, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : 'plaintext';
            const inline = !className;
            const codeContent = String(children);

            // 檢查是否包含引用標籤
            if (codeContent.includes('{{CITATION:') || codeContent.includes('{{FILE:')) {
              const processed = processTextWithCitations(codeContent);
              return <>{processed}</>;
            }

            return !inline && match ? (
              <SyntaxHighlighter
                style={vscDarkPlus}
                language={language}
                PreTag="div"
                customStyle={{
                  margin: '1em 0',
                  borderRadius: '6px',
                  fontSize: '13px'
                }}
                {...props}
              >
                {codeContent.replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code
                className={className}
                style={{
                  background: '#f5f5f5',
                  padding: '2px 6px',
                  borderRadius: '3px',
                  fontSize: '0.9em',
                  fontFamily: 'monospace'
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          // 自定義段落樣式 - 處理引用標籤
          p({ children }) {
            const processed = processChildren(children);
            return <p style={{ marginBottom: '0.8em', lineHeight: '1.6' }}>{processed}</p>;
          },
          // 自定義列表樣式
          ul({ children }) {
            return <ul style={{
              paddingLeft: '1.5em',
              marginBottom: '0.8em',
              marginTop: '0.5em',
              listStyleType: 'disc',
              listStylePosition: 'outside'
            }}>{children}</ul>;
          },
          ol({ children }) {
            return <ol style={{
              paddingLeft: '1.5em',
              marginBottom: '0.8em',
              marginTop: '0.5em',
              listStyleType: 'decimal',
              listStylePosition: 'outside'
            }}>{children}</ol>;
          },
          li({ children }) {
            const processed = processChildren(children);
            return <li style={{ marginBottom: '0.4em', lineHeight: '1.6', display: 'list-item' }}>{processed}</li>;
          },
          // 自定義標題樣式
          h1({ children }) {
            return <h1 style={{ fontSize: '1.5em', fontWeight: 600, marginTop: '1em', marginBottom: '0.5em' }}>{children}</h1>;
          },
          h2({ children }) {
            return <h2 style={{ fontSize: '1.3em', fontWeight: 600, marginTop: '0.8em', marginBottom: '0.4em' }}>{children}</h2>;
          },
          h3({ children }) {
            return <h3 style={{ fontSize: '1.1em', fontWeight: 600, marginTop: '0.6em', marginBottom: '0.3em' }}>{children}</h3>;
          },
          // 自定義引用樣式
          blockquote({ children }) {
            return (
              <blockquote
                style={{
                  borderLeft: '3px solid #d1d5db',
                  paddingLeft: '1em',
                  marginLeft: '0',
                  color: '#6b7280',
                  fontStyle: 'italic'
                }}
              >
                {children}
              </blockquote>
            );
          },
          // 自定義超連結樣式
          a({ children, href }) {
            // 處理 citation:N 格式的引用鏈接
            if (href && href.startsWith('citation:')) {
              const docId = parseInt(href.replace('citation:', ''), 10);
              return (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 8px',
                    background: '#e6f7ff',
                    color: '#1890ff',
                    borderRadius: '4px',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    border: '1px solid #91d5ff',
                    margin: '0 2px'
                  }}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (onCitationClick) onCitationClick(docId);
                  }}
                >
                  <span>📄</span>
                  <span>{children}</span>
                </span>
              );
            }

            // 處理文件名連結
            const hasFileExt = href && FILE_EXTENSIONS.some(ext =>
              href.toLowerCase().endsWith(`.${ext}`)
            );

            if (hasFileExt && href) {
              const matchedDoc = documentPool.find(doc =>
                doc.filename === href ||
                doc.filename.includes(href) ||
                href.includes(doc.filename)
              );

              return (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 8px',
                    background: '#f0f5ff',
                    color: '#1890ff',
                    borderRadius: '4px',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    border: '1px solid #adc6ff',
                    margin: '0 2px'
                  }}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    console.log('📄 文件連結點擊:', href, matchedDoc);
                    if (matchedDoc && onFileClick) {
                      onFileClick(matchedDoc.document_id);
                    } else if (matchedDoc && onCitationClick) {
                      const idx = documentPool.findIndex(d => d.document_id === matchedDoc.document_id);
                      if (idx >= 0) onCitationClick(idx + 1);
                    }
                  }}
                >
                  <span>{getFileIcon(href)}</span>
                  <span>{children}</span>
                </span>
              );
            }

            // 普通連結
            return (
              <a
                href={href || '#'}
                style={{
                  color: '#1890ff',
                  textDecoration: 'underline',
                  fontWeight: 500,
                  cursor: 'pointer'
                }}
                onClick={(e) => {
                  if (href && (href.startsWith('http://') || href.startsWith('https://'))) {
                    e.preventDefault();
                    window.open(href, '_blank', 'noopener,noreferrer');
                  }
                }}
                title={href || undefined}
              >
                {children}
              </a>
            );
          },
          // 處理 strong 標籤
          strong({ children }) {
            const processed = processChildren(children);
            return <strong style={{ fontWeight: 600 }}>{processed}</strong>;
          },
          // 自定義表格樣式
          table({ children }) {
            return (
              <div style={{ overflowX: 'auto', marginBottom: '1em' }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  {children}
                </table>
              </div>
            );
          },
          th({ children }) {
            return (
              <th style={{
                border: '1px solid #d1d5db',
                padding: '8px',
                background: '#f9fafb',
                fontWeight: 600
              }}>
                {children}
              </th>
            );
          },
          td({ children }) {
            return (
              <td style={{ border: '1px solid #d1d5db', padding: '8px' }}>
                {children}
              </td>
            );
          }
        }}
      >
        {preprocessedContent}
      </ReactMarkdown>
    );
  }, [content, onCitationClick, documentPool, onFileClick]);

  return (
    <div className="streamed-markdown">
      {renderedContent}
      {isStreaming && (
        <span
          className="typing-cursor"
          style={{
            display: 'inline-block',
            width: '8px',
            height: '16px',
            background: '#1890ff',
            marginLeft: '2px',
            animation: 'blink 1s step-end infinite'
          }}
        >
          ▊
        </span>
      )}
    </div>
  );
};
