"""
行號標記服務

為文檔內容添加行號標記，支援長文檔分批處理。
用於 AI 邏輯分塊時的座標系統。
"""

from typing import Tuple, Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class DocumentBatch:
    """文檔批次資訊"""
    batch_index: int
    content: str
    global_line_start: int
    global_line_end: int
    page_range: Optional[Tuple[int, int]] = None  # (start_page, end_page) 1-indexed


@dataclass
class BatchConfig:
    """分批配置"""
    strategy: str  # "by_page" | "by_chars"
    batch_size: int
    unit: str  # "pages" | "characters"
    overlap_chars: int = 500  # 字元重疊
    overlap_lines: int = 10   # 行重疊


# 配置常數
BATCH_SIZE_PAGES = 5          # PDF/Word 每批頁數
BATCH_SIZE_CHARS = 10000      # 純文字每批字數
BATCH_OVERLAP_CHARS = 500     # 批次間重疊字數
LENGTH_THRESHOLD = 10000      # 分批閾值 (10K 字元)


def add_line_markers(
    text: str,
    global_start: int = 1
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """
    為文本添加行號標記

    Args:
        text: 原始文本
        global_start: 全局行號起始值 (跨批次連續)

    Returns:
        marked_text: 帶行號標記的文本
        line_mapping: 行號到位置的映射

    Example:
        輸入: "第一行內容\\n第二行內容"
        輸出: "[L001] 第一行內容\\n[L002] 第二行內容", {
            "L001": {"global_line": 1, "char_start": 0, "char_end": 5, ...},
            "L002": {"global_line": 2, "char_start": 6, "char_end": 11, ...}
        }
    """
    if not text:
        return "", {}

    lines = text.split('\n')
    marked_lines = []
    line_mapping = {}
    char_offset = 0

    for i, line in enumerate(lines):
        global_line = global_start + i
        line_id = f"L{global_line:03d}"

        marked_lines.append(f"[{line_id}] {line}")

        line_mapping[line_id] = {
            "local_index": i,
            "global_line": global_line,
            "char_start": char_offset,
            "char_end": char_offset + len(line),
            "length": len(line),
            "content_preview": line[:50] + "..." if len(line) > 50 else line
        }

        char_offset += len(line) + 1  # +1 for newline

    return '\n'.join(marked_lines), line_mapping


# 預編譯正則表達式以提高效能
_LINE_MARKER_PATTERN = re.compile(r'\[L\d{3,}\]\s*')


def remove_line_markers(text: str) -> str:
    """
    從文本中移除行號標記
    
    將 "[L001] 內容" 格式轉換為純 "內容"
    
    Args:
        text: 可能包含行號標記的文本
        
    Returns:
        移除行號標記後的純文本
    """
    return _LINE_MARKER_PATTERN.sub('', text)


def extract_text_by_line_range(
    original_text: str,
    line_mapping: Dict[str, Dict[str, Any]],
    start_line: str,
    end_line: str,
    strip_line_markers: bool = True
) -> str:
    """
    根據行號範圍從原始文本中提取內容

    Args:
        original_text: 原始文本 (可能包含行號標記)
        line_mapping: 行號映射
        start_line: 起始行號 (如 "L001")
        end_line: 結束行號 (如 "L010")
        strip_line_markers: 是否移除行號標記 (預設 True)

    Returns:
        提取的文本內容 (預設移除行號標記)
    """
    if start_line not in line_mapping or end_line not in line_mapping:
        logger.warning(f"行號範圍無效: {start_line} - {end_line}")
        return ""

    start_info = line_mapping[start_line]
    end_info = line_mapping[end_line]

    char_start = start_info["char_start"]
    char_end = end_info["char_end"]

    extracted = original_text[char_start:char_end]
    
    # 移除行號標記（如果需要）
    if strip_line_markers:
        extracted = remove_line_markers(extracted)
    
    return extracted


def determine_batch_strategy(file_type: str, text_length: int) -> Optional[BatchConfig]:
    """
    根據文檔類型和大小決定分批策略

    Args:
        file_type: 文件類型 (如 ".pdf", ".docx", ".txt")
        text_length: 文本長度

    Returns:
        BatchConfig 或 None (不需要分批)
    """
    # 短文檔不需要分批
    if text_length < LENGTH_THRESHOLD:
        return None

    file_ext = file_type.lower() if file_type else ""

    if file_ext in ['.pdf', '.docx', '.doc']:
        return BatchConfig(
            strategy="by_page",
            batch_size=BATCH_SIZE_PAGES,
            unit="pages",
            overlap_lines=10
        )
    else:
        # 純文字 (.txt, .md, 或其他)
        return BatchConfig(
            strategy="by_chars",
            batch_size=BATCH_SIZE_CHARS,
            unit="characters",
            overlap_chars=BATCH_OVERLAP_CHARS
        )


def split_text_into_batches(
    text: str,
    batch_config: BatchConfig
) -> List[DocumentBatch]:
    """
    按字數將文本分批

    Args:
        text: 原始文本
        batch_config: 分批配置

    Returns:
        批次列表
    """
    if batch_config.strategy != "by_chars":
        raise ValueError("此函數僅支援 by_chars 策略")

    batches = []
    text_length = len(text)
    global_line_offset = 1
    char_start = 0
    batch_index = 0

    while char_start < text_length:
        char_end = min(char_start + batch_config.batch_size, text_length)

        # 尋找最近的換行符，避免切斷行
        if char_end < text_length:
            # 在 batch_size 附近找換行符
            search_start = max(char_start, char_end - 200)
            search_end = min(text_length, char_end + 200)
            newline_pos = text.rfind('\n', search_start, search_end)

            if newline_pos > char_start:
                char_end = newline_pos + 1

        batch_content = text[char_start:char_end]
        lines_in_batch = batch_content.count('\n') + 1

        batches.append(DocumentBatch(
            batch_index=batch_index,
            content=batch_content,
            global_line_start=global_line_offset,
            global_line_end=global_line_offset + lines_in_batch - 1,
            page_range=None
        ))

        global_line_offset += lines_in_batch
        batch_index += 1

        # 下一批次從重疊區開始 (如果不是最後一批)
        if char_end < text_length:
            char_start = max(char_start + 1, char_end - batch_config.overlap_chars)
        else:
            break

    logger.info(f"文本已分為 {len(batches)} 批，總行數約 {global_line_offset - 1}")
    return batches


def process_text_with_line_markers(
    text: str,
    file_type: str = ""
) -> Tuple[str, Dict[str, Dict[str, Any]], Optional[List[DocumentBatch]]]:
    """
    處理文本並添加行號標記

    自動判斷是否需要分批處理：
    - 短文檔 (< 10K): 直接處理
    - 長文檔 (>= 10K): 分批處理

    Args:
        text: 原始文本
        file_type: 文件類型

    Returns:
        marked_text: 帶行號標記的完整文本
        line_mapping: 行號映射
        batches: 批次列表 (如果分批) 或 None
    """
    text_length = len(text)
    batch_config = determine_batch_strategy(file_type, text_length)

    if batch_config is None:
        # 短文檔：直接處理
        marked_text, line_mapping = add_line_markers(text)
        logger.info(f"短文檔處理完成，共 {len(line_mapping)} 行")
        return marked_text, line_mapping, None

    # 長文檔：分批處理
    if batch_config.strategy == "by_chars":
        batches = split_text_into_batches(text, batch_config)

        # 為完整文本生成行號映射
        marked_text, line_mapping = add_line_markers(text)

        # 為每個批次添加帶行號的內容
        for batch in batches:
            batch_marked, _ = add_line_markers(
                batch.content,
                global_start=batch.global_line_start
            )
            batch.content = batch_marked

        logger.info(f"長文檔分批處理完成，共 {len(batches)} 批，{len(line_mapping)} 行")
        return marked_text, line_mapping, batches

    # PDF/Word 按頁分批 (需要外部處理)
    marked_text, line_mapping = add_line_markers(text)
    logger.info(f"PDF/Word 文檔標記完成，共 {len(line_mapping)} 行，需外部分頁處理")
    return marked_text, line_mapping, None


def get_batch_context_prompt(
    batch: DocumentBatch,
    total_batches: int
) -> str:
    """
    生成批次上下文提示，告知 AI 當前處理的是哪一批

    Args:
        batch: 當前批次
        total_batches: 總批次數

    Returns:
        上下文提示字串
    """
    return (
        f"這是文檔的第 {batch.batch_index + 1}/{total_batches} 批，"
        f"行號範圍 L{batch.global_line_start:03d} - L{batch.global_line_end:03d}。"
    )


# ============================================================
# Phase 3: 智能子分塊向量化支援函數
# ============================================================

def smart_split_text(
    text: str,
    max_length: int = 480,
    overlap: int = 50
) -> List[str]:
    """
    智能分割長文本為多個子塊

    特點：
    - 優先在句子邊界處切分
    - 支援中英文混合
    - 保持重疊以確保上下文連貫性

    Args:
        text: 要分割的文本
        max_length: 每個子塊的最大長度
        overlap: 子塊之間的重疊字符數

    Returns:
        子塊列表
    """
    if not text or len(text) <= max_length:
        return [text] if text else []

    sub_chunks = []
    text_length = len(text)
    start = 0

    while start < text_length:
        # 計算這個子塊的結束位置
        end = min(start + max_length, text_length)

        # 如果不是最後一塊，嘗試在句子邊界處切分
        if end < text_length:
            # 在 end 附近尋找句子邊界
            search_start = max(start, end - 100)  # 往前搜索 100 字符
            search_end = min(text_length, end + 50)  # 往後搜索 50 字符

            # 尋找最近的句子邊界
            best_break = -1
            for sep in ['。', '！', '？', '；', '\n', '.', '!', '?', ';']:
                # 優先在 end 之前找
                pos = text.rfind(sep, search_start, end)
                if pos > start and pos > best_break:
                    best_break = pos + 1  # 包含分隔符

                # 如果在 end 之前沒找到，嘗試在 end 之後找
                if best_break == -1:
                    pos = text.find(sep, end, search_end)
                    if pos != -1 and pos < search_end:
                        best_break = pos + 1

            if best_break > start:
                end = best_break

        # 提取子塊
        chunk = text[start:end].strip()
        if chunk:
            sub_chunks.append(chunk)

        # 下一個子塊的起始位置（帶重疊）
        if end >= text_length:
            break
        start = max(start + 1, end - overlap)

    logger.debug(f"文本 ({len(text)} 字符) 分割為 {len(sub_chunks)} 個子塊")
    return sub_chunks


@dataclass
class ChunkVectorizationResult:
    """單個 chunk 的向量化結果"""
    content: str                    # 向量化的內容
    strategy: str                   # 使用的策略: "hybrid" | "raw_only" | "sub_chunked"
    chunk_id: int                   # 原始 chunk ID
    sub_index: int                  # 子塊索引 (0 表示無子分塊或第一塊)
    total_sub_chunks: int           # 總子塊數
    start_line: str                 # 起始行號
    end_line: str                   # 結束行號
    chunk_type: str                 # 區塊類型
    summary: str                    # 區塊摘要


def process_logical_chunk_for_vectorization(
    chunk_id: int,
    start_id: str,
    end_id: str,
    chunk_type: str,
    summary: str,
    raw_text: str,
    hybrid_threshold: int = 350,
    safe_length: int = 480,
    sub_chunk_overlap: int = 50
) -> List[ChunkVectorizationResult]:
    """
    處理單個 logical chunk 的向量化

    智能選擇向量化策略：
    - 短 chunk (≤ hybrid_threshold): 使用混合增強 [Summary] + [Content]
    - 中等 chunk (hybrid_threshold < len ≤ safe_length): 只用原文
    - 長 chunk (> safe_length): 子分塊

    Args:
        chunk_id: 區塊 ID
        start_id: 起始行號 (如 "L001")
        end_id: 結束行號 (如 "L010")
        chunk_type: 區塊類型 (如 "paragraph", "list")
        summary: 區塊摘要
        raw_text: 從 line_mapping 提取的原文
        hybrid_threshold: 混合增強閾值
        safe_length: 單向量最大長度
        sub_chunk_overlap: 子分塊重疊

    Returns:
        向量化結果列表
    """
    results = []
    text_length = len(raw_text)

    if text_length <= hybrid_threshold:
        # === 短 chunk：使用混合增強 ===
        payload = f"[Summary]: {summary}\n[Content]: {raw_text}"
        results.append(ChunkVectorizationResult(
            content=payload,
            strategy="hybrid",
            chunk_id=chunk_id,
            sub_index=0,
            total_sub_chunks=1,
            start_line=start_id,
            end_line=end_id,
            chunk_type=chunk_type,
            summary=summary
        ))
        logger.debug(f"Chunk {chunk_id}: 使用混合增強策略 ({text_length} 字符)")

    elif text_length <= safe_length:
        # === 中等 chunk：只用原文（完整） ===
        results.append(ChunkVectorizationResult(
            content=raw_text,
            strategy="raw_only",
            chunk_id=chunk_id,
            sub_index=0,
            total_sub_chunks=1,
            start_line=start_id,
            end_line=end_id,
            chunk_type=chunk_type,
            summary=summary
        ))
        logger.debug(f"Chunk {chunk_id}: 使用原文策略 ({text_length} 字符)")

    else:
        # === 長 chunk：子分塊 ===
        sub_chunks = smart_split_text(raw_text, safe_length, sub_chunk_overlap)
        total = len(sub_chunks)

        for i, sub_text in enumerate(sub_chunks):
            results.append(ChunkVectorizationResult(
                content=sub_text,
                strategy="sub_chunked",
                chunk_id=chunk_id,
                sub_index=i,
                total_sub_chunks=total,
                start_line=start_id,
                end_line=end_id,
                chunk_type=chunk_type,
                summary=summary
            ))

        logger.debug(f"Chunk {chunk_id}: 使用子分塊策略 ({text_length} 字符 → {total} 個子塊)")

    return results
