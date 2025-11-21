# 推理鏈組件整合指南

## 📋 整合步驟

### 1. 更新 QASession Interface

在 `AIQAPage.tsx` 的 `QASession` interface 中添加推理步驟字段：

```typescript
interface QASession {
  id: string;
  question: string;
  answer: string;
  timestamp: Date;
  sourceDocuments: string[];
  tokensUsed: number;
  processingTime: number;
  confidenceScore?: number;
  queryRewriteResult?: QueryRewriteResult | null;
  llmContextDocuments?: LLMContextDocument[] | null;
  semanticSearchContexts?: SemanticContextDocument[] | null;
  detailedDocumentDataFromAiQuery?: any[] | null;
  detailedQueryReasoning?: string | null;
  sessionId?: string;
  usedSettings?: AIQASettingsConfig;
  classification?: any;
  workflowState?: any;
  nextAction?: string;
  // ✅ 新增：推理步驟
  reasoningSteps?: ReasoningStep[];
  isStreaming?: boolean;
}
```

### 2. Import 推理鏈組件

在文件頂部添加 import：

```typescript
import ReasoningChainDisplay, { ReasoningStep } from '../components/ReasoningChainDisplay';
```

### 3. 添加推理步驟狀態

在組件的狀態聲明部分添加：

```typescript
// 推理鏈相關狀態
const [currentReasoningSteps, setCurrentReasoningSteps] = useState<ReasoningStep[]>([]);
const [isReasoningStreaming, setIsReasoningStreaming] = useState(false);
```

### 4. 修改流式問答處理（使用 streamQA）

如果你想使用流式API，需要修改 `handleAskQuestion` 函數：

```typescript
import { streamQA } from '../services/streamQAService';

const handleAskQuestion = async (customQuestion?: string) => {
  const questionToAsk = customQuestion || question.trim();
  
  if (!questionToAsk.trim()) {
    showPCMessage('請輸入問題', 'error');
    return;
  }

  try {
    setIsAsking(true);
    setIsReasoningStreaming(true);
    setCurrentReasoningSteps([]); // 重置推理步驟
    
    let fullAnswer = '';
    const tempReasoningSteps: ReasoningStep[] = [];
    const startTime = Date.now();
    
    // 使用流式API
    await streamQA(
      {
        question: questionToAsk,
        conversation_id: currentConversationId || undefined,
        model_preference: aiQASettings.preferredModel,
        // ... 其他參數
      },
      {
        // 處理進度事件（包含推理內容）
        onProgress: (stage, message, detail) => {
          console.log('📊 Progress:', { stage, message, detail });
          
          // 將進度事件轉換為推理步驟
          if (stage === 'reasoning') {
            // 處理後端發送的推理內容
            const step: ReasoningStep = {
              type: 'thought', // 可根據 detail 調整
              stage,
              message,
              detail,
              status: 'done',
              timestamp: Date.now()
            };
            tempReasoningSteps.push(step);
            setCurrentReasoningSteps([...tempReasoningSteps]);
          } else if (stage === 'classifying') {
            tempReasoningSteps.push({
              type: 'thought',
              stage: 'classification',
              message: message,
              status: 'active',
              timestamp: Date.now()
            });
            setCurrentReasoningSteps([...tempReasoningSteps]);
          } else if (stage === 'searching') {
            tempReasoningSteps.push({
              type: 'action',
              stage: 'search',
              message: '正在搜索相關文檔...',
              status: 'active',
              timestamp: Date.now()
            });
            setCurrentReasoningSteps([...tempReasoningSteps]);
          }
        },
        
        // 處理答案塊
        onChunk: (text) => {
          fullAnswer += text;
          // 更新 UI 顯示流式答案
        },
        
        // 處理完成
        onComplete: (completeAnswer) => {
          setIsReasoningStreaming(false);
          
          // 更新所有步驟狀態為 done
          const finalSteps = tempReasoningSteps.map(s => ({ ...s, status: 'done' as const }));
          
          // 添加答案生成完成步驟
          finalSteps.push({
            type: 'observation',
            stage: 'complete',
            message: '答案生成完成',
            status: 'done',
            timestamp: Date.now()
          });
          
          setCurrentReasoningSteps(finalSteps);
          
          // 保存到歷史記錄
          const newSession: QASession = {
            id: `qa-${Date.now()}`,
            question: questionToAsk,
            answer: fullAnswer || completeAnswer,
            timestamp: new Date(),
            sourceDocuments: [],
            tokensUsed: 0,
            processingTime: (Date.now() - startTime) / 1000,
            reasoningSteps: finalSteps, // ✅ 保存推理步驟
            isStreaming: false
          };
          
          setQAHistory([newSession, ...qaHistory]);
          setQuestion('');
          setIsAsking(false);
        },
        
        // 處理錯誤
        onError: (error) => {
          console.error('❌ Stream error:', error);
          showPCMessage(`問答失敗: ${error}`, 'error');
          setIsAsking(false);
          setIsReasoningStreaming(false);
        }
      }
    );
    
  } catch (error) {
    console.error('問答失敗:', error);
    showPCMessage('問答失敗', 'error');
    setIsAsking(false);
    setIsReasoningStreaming(false);
  }
};
```

### 5. 在 UI 中顯示推理鏈

在顯示答案的位置（通常在歷史記錄渲染部分）添加推理鏈展示：

```typescript
{/* 問答歷史渲染 */}
{qaHistory.map((session) => (
  <div key={session.id} className="qa-session-container">
    {/* 用戶問題 */}
    <div className="user-question-bubble">
      <UserOutlined />
      <Text>{session.question}</Text>
    </div>
    
    {/* AI 回答容器 */}
    <div className="ai-answer-container">
      <RobotOutlined className="ai-icon" />
      
      <div className="ai-content">
        {/* ✅ 推理鏈展示 */}
        {session.reasoningSteps && session.reasoningSteps.length > 0 && (
          <ReasoningChainDisplay
            steps={session.reasoningSteps}
            isStreaming={session.isStreaming || false}
            processingTime={session.processingTime}
          />
        )}
        
        {/* 答案內容 */}
        <div className="answer-content">
          <MarkdownRenderer content={session.answer} />
        </div>
        
        {/* 其他信息（文檔引用、tokens等） */}
        {/* ... */}
      </div>
    </div>
  </div>
))}
```

### 6. 處理當前流式輸出

如果有正在流式輸出的答案，也要顯示實時推理鏈：

```typescript
{/* 當前正在回答的問題 */}
{isAsking && (
  <div className="current-qa-session">
    <div className="user-question-bubble">
      <UserOutlined />
      <Text>{question}</Text>
    </div>
    
    <div className="ai-answer-container">
      <RobotOutlined className="ai-icon" />
      
      <div className="ai-content">
        {/* ✅ 實時推理鏈 */}
        {currentReasoningSteps.length > 0 && (
          <ReasoningChainDisplay
            steps={currentReasoningSteps}
            isStreaming={isReasoningStreaming}
            processingTime={undefined}
          />
        )}
        
        {/* 流式答案 */}
        <div className="answer-content streaming">
          <MarkdownRenderer content={currentAnswer} />
          <span className="typing-cursor">▋</span>
        </div>
      </div>
    </div>
  </div>
)}
```

## 🎨 樣式建議

添加一些 CSS 來配合 Neo-Brutalism 風格：

```css
/* AI 回答容器 */
.ai-answer-container {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
  animation: fadeIn 0.3s ease-out;
}

.ai-icon {
  width: 40px;
  height: 40px;
  background: #29bf12;
  border: 2px solid #000;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  box-shadow: 2px 2px 0px black;
  flex-shrink: 0;
}

.ai-content {
  flex: 1;
  min-width: 0;
}

.user-question-bubble {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #000;
  color: white;
  padding: 12px 20px;
  border-radius: 16px 16px 0 16px;
  margin-bottom: 16px;
  margin-left: auto;
  max-width: 80%;
  box-shadow: 4px 4px 0px rgba(0,0,0,0.2);
}

.answer-content {
  background: white;
  border: 2px solid #000;
  border-radius: 12px;
  padding: 20px;
  margin-top: 16px;
  box-shadow: 4px 4px 0px black;
}

.typing-cursor {
  display: inline-block;
  color: #29bf12;
  animation: blink 1s infinite;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}
```

## 🔧 後端數據格式

確保後端發送的推理事件格式正確：

```python
# 在 qa_orchestrator.py 中
yield StreamEvent('progress', {
    'stage': 'reasoning',
    'message': '💭 AI 推理',
    'detail': classification.reasoning
})
```

前端會接收到：

```typescript
{
  type: 'progress',
  stage: 'reasoning',
  message: '💭 AI 推理',
  detail: '我需要先理解用戶問題的意圖...'
}
```

## ✅ 完成檢查清單

- [ ] 更新 QASession interface
- [ ] Import ReasoningChainDisplay 組件
- [ ] 添加推理步驟狀態變數
- [ ] 修改流式問答處理邏輯
- [ ] 在 UI 中整合推理鏈顯示
- [ ] 添加配套 CSS 樣式
- [ ] 測試流式輸出效果
- [ ] 測試推理鏈折疊/展開
- [ ] 測試移動端響應式

## 🎯 預期效果

完成後，用戶在提問時會看到：

1. ✅ 用戶問題以黑色氣泡顯示
2. ✅ AI 回答容器包含：
   - 推理鏈展示（可折疊的步驟）
   - 最終答案（Markdown 格式）
   - 文檔引用
3. ✅ 流式輸出時實時更新推理步驟
4. ✅ Neo-Brutalism 風格（黑邊框、硬陰影、鮮明顏色）

這樣就完成了類似 Cursor/Windsurf 的流式狀態機效果！
