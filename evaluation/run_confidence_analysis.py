import asyncio
import json
import os
import sys
from pathlib import Path
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import aiohttp

# --- Load Environment Variables ---
from dotenv import load_dotenv

project_root_path = Path(__file__).resolve().parents[2]

# 依序檢查多個可能的 .env 路徑
env_paths_to_check = [
    project_root_path / 'evaluation' / '.env',
    project_root_path / '.env'
]

dotenv_path = None
for path in env_paths_to_check:
    if path.exists():
        dotenv_path = path
        break

if dotenv_path:
    print(f"Loading environment variables from: {dotenv_path}")
    # 使用 override=True 確保檔案中的設定能覆寫任何已存在的環境變數
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    print(f"FATAL: .env file not found in any of the expected locations: {env_paths_to_check}")
    sys.exit(1)

class ApiClient:
    """一個簡單的 API 客戶端，用於登入和搜索"""
    def __init__(self):
        self.api_base_url = os.getenv('API_URL', 'http://127.0.0.1:8000')
        self.username = os.getenv('USERNAME')
        self.password = os.getenv('PASSWORD')
        self.session = None
        self.access_token = None

        if not all([self.api_base_url, self.username, self.password]):
            print("FATAL: API_URL, USERNAME, or PASSWORD not found in .env file.")
            sys.exit(1)

    async def initialize(self):
        """初始化 aiohttp session 並登入"""
        self.session = aiohttp.ClientSession()
        if not await self.login():
            raise Exception("API Login failed. Please check credentials and backend status.")
        print("✅ API 客戶端初始化並登入成功。")

    async def login(self) -> bool:
        """登入並獲取 JWT token"""
        login_url = f"{self.api_base_url}/api/v1/auth/token"
        login_data = {"username": self.username, "password": self.password}
        print(f"正在嘗試登入: {login_url}")
        try:
            async with self.session.post(login_url, data=login_data) as response:
                response.raise_for_status()
                result = await response.json()
                self.access_token = result.get("access_token")
                if self.access_token:
                    return True
                return False
        except Exception as e:
            print(f"登入失敗: {e}")
            return False

    def get_auth_headers(self) -> dict:
        if not self.access_token:
            raise ValueError("Access token is not available.")
        return {"Authorization": f"Bearer {self.access_token}"}

    async def search(self, query: str, top_k: int, threshold: float) -> list:
        """執行傳統單階段搜索"""
        search_url = f"{self.api_base_url}/api/v1/vector-db/semantic-search"
        payload = {
            "query": query,
            "top_k": top_k,
            "similarity_threshold": threshold,
            "search_type": "legacy",  # 使用 'legacy' 模式，對應傳統單階段搜索
            "enable_hybrid_search": False
        }
        try:
            async with self.session.post(search_url, json=payload, headers=self.get_auth_headers()) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"\n搜索API請求失敗 ({response.status}) for query '{query[:30]}...'")
                    return []
        except Exception as e:
            print(f"\n搜索API請求時發生錯誤 for query '{query[:30]}...': {e}")
            return []

    async def close(self):
        """關閉 aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()

# --- 主要評估邏輯 ---

def load_test_cases(file_path: Path) -> list:
    """從 JSON 文件加載測試案例"""
    print(f"正在從 {file_path} 加載測試案例...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"成功加載 {len(data)} 個測試案例。")
        return data
    except Exception as e:
        print(f"錯誤：加載測試案例失敗: {e}")
        return []

async def run_single_test(api_client: ApiClient, test_case: dict) -> tuple[bool, float, str]:
    """執行單個測試案例 (API 版本)"""
    question = test_case.get("question")
    expected_doc_ids = set(test_case.get("expected_relevant_doc_ids", []))

    if not question or not expected_doc_ids:
        return False, 0.0, "skipped"

    try:
        # 使用 API Client 執行搜索
        search_results = await api_client.search(
            query=question,
            top_k=5,
            threshold=0.1
        )

        if not search_results:
            return False, 0.0, "no_results"

        # 解析 API 回傳的結果
        for result in search_results:
            doc_id = result.get("document_id")
            if doc_id and doc_id in expected_doc_ids:
                return True, result.get("similarity_score", 0.0), "hit"

        return False, search_results[0].get("similarity_score", 0.0), "miss"

    except Exception as e:
        print(f"\n處理查詢時出錯 '{question[:30]}...': {e}")
        return False, 0.0, "error"

def plot_score_distribution(scores: list[float], output_path: Path):
    """繪製分數分佈直方圖"""
    if not scores:
        print("沒有可供繪圖的正確命中分數。")
        return

    print(f"\n正在繪製 {len(scores)} 個正確命中的分數分佈圖...")
    plt.style.use('seaborn-v0_8-whitegrid')
    plt.figure(figsize=(12, 7))
    
    sns.histplot(scores, bins=20, kde=True, color='skyblue')
    
    mean_score = pd.Series(scores).mean()
    median_score = pd.Series(scores).median()
    plt.axvline(mean_score, color='red', linestyle='--', label=f'平均分: {mean_score:.3f}')
    plt.axvline(median_score, color='green', linestyle='-', label=f'中位數: {median_score:.3f}')
    
    plt.title('正確命中案例的相似度分數分佈圖', fontsize=16)
    plt.xlabel('相似度分數 (Confidence Score)', fontsize=12)
    plt.ylabel('案例數量', fontsize=12)
    plt.legend()
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    
    try:
        plt.savefig(output_path, dpi=300)
        print(f"✅ 分佈圖已成功儲存至: {output_path}")
    except Exception as e:
        print(f"錯誤：儲存圖片失敗: {e}")

async def main():
    """主執行函數"""
    script_dir = Path(__file__).parent
    test_file_path = project_root_path / 'evaluation' / 'QA_dataset.json'
    output_image_path = script_dir / 'confidence_distribution.png'
    
    test_cases = load_test_cases(test_file_path)
    if not test_cases:
        return

    api_client = ApiClient()
    await api_client.initialize()

    hit_scores = []
    miss_scores_top1 = []
    
    print("\n開始執行 API 評估...")
    for test_case in tqdm(test_cases, desc="評估進度"):
        is_hit, score, status = await run_single_test(api_client, test_case)
        if status == "hit":
            hit_scores.append(score)
        elif status == "miss":
            miss_scores_top1.append(score)

    await api_client.close()

    print("\n--- 測試結果摘要 ---")
    total_cases = len(test_cases)
    hit_count = len(hit_scores)
    miss_count = len(miss_scores_top1)
    other_count = total_cases - hit_count - miss_count
    
    if total_cases > 0:
        hit_rate = (hit_count / total_cases) * 100
        print(f"總案例數: {total_cases}")
        print(f"✅ 正確命中: {hit_count} ({hit_rate:.2f}%)")
        print(f"❌ 未命中:   {miss_count}")
        print(f"⚪️ 其他 (錯誤/跳過): {other_count}")

    plot_score_distribution(hit_scores, output_image_path)
    
    if hit_scores:
        df = pd.DataFrame(hit_scores, columns=['score'])
        print("\n--- 分數統計數據 (僅限正確命中) ---")
        print(df.describe())
        print("\n根據以上數據，您可以選擇一個閾值。例如，25% 分位數 (0.75-0.85 之間) 可能是一個不錯的起點。")
        print("這意味著您將能以高可信度正確處理約 75% 的命中案例，同時將更多資源留給分數較低的模糊案例進行 AI 優化。")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main()) 