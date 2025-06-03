// mainCopilotServer.js (Conceptual Example)
import dotenv from 'dotenv';
import {createServer} from 'node:http'; // Or use Express, Next.js API routes, etc.
import { CopilotRuntime,GoogleGenerativeAIAdapter,copilotRuntimeNodeHttpEndpoint } from '@copilotkit/runtime'; // Or GoogleGenerativeAIAdapter, etc.

// 1. 設定您的 LLM Adapter
// 您需要提供您的 API 金鑰和其他必要的設定
dotenv.config();
const serviceAdapter = new GoogleGenerativeAIAdapter({ model: "gemini-2.0-flash" });

const server = createServer((req, res) => {
    const runtime = new CopilotRuntime({
      remoteEndpoints: [
        {
          url: 'http://localhost:8000/api/v1/copilotkit_actions'
        },
      ],
    });
    const handler = copilotRuntimeNodeHttpEndpoint({
      endpoint: '/copilotkit',
      runtime,
      serviceAdapter,
    });
   
    return handler(req, res);
  });

const PORT = 3001; // 與前端 index.tsx 中設定的端口一致
server.listen(PORT, () => {
  console.log(`Main CopilotKit Node.js Runtime listening on http://localhost:${PORT}/api/copilotkit`);
  console.log(`This runtime is configured to use Python actions from http://localhost:8000/api/v1/copilotkit_actions`);
});