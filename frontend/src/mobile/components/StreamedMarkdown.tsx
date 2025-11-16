import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';

interface StreamedMarkdownProps {
  content: string;
  isStreaming?: boolean;
}

/**
 * 流式 Markdown 渲染組件
 * 
 * 性能優化：
 * 1. 使用 useMemo 緩存渲染結果，只在內容變化時重新渲染
 * 2. 代碼塊使用 Syntax Highlighter 高亮顯示
 * 3. 支持 GitHub Flavored Markdown (GFM)
 * 
 * 參考 ChatGPT/Gemini 的最佳實踐
 */
export const StreamedMarkdown: React.FC<StreamedMarkdownProps> = ({ 
  content, 
  isStreaming = false 
}) => {
  // 使用 useMemo 緩存 Markdown 渲染結果
  // 只有當內容變化時才重新渲染，避免每次 state 變化都重新解析
  const renderedContent = useMemo(() => {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 自定義代碼塊渲染，支持語法高亮
          code({ node, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : 'plaintext';
            const inline = !className;
            
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
                {String(children).replace(/\n$/, '')}
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
          // 自定義段落樣式
          p({ children }) {
            return <p style={{ marginBottom: '0.8em', lineHeight: '1.6' }}>{children}</p>;
          },
          // 自定義列表樣式 - 顯示項目符號
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
            return <li style={{ 
              marginBottom: '0.4em',
              lineHeight: '1.6',
              display: 'list-item'
            }}>{children}</li>;
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
          // 自定義超連結樣式（禁用導航，只顯示樣式）
          a({ children, href }) {
            return (
              <span 
                style={{ 
                  color: '#1890ff',
                  textDecoration: 'none',
                  fontWeight: 500,
                  cursor: 'text'
                }}
                title={href || undefined}
              >
                {children}
              </span>
            );
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
        {content}
      </ReactMarkdown>
    );
  }, [content]); // 只有 content 變化時才重新渲染

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
