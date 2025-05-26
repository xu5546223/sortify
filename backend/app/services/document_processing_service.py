"""
Service for processing uploaded documents, including text extraction
and potentially other pre-processing steps before AI analysis.
"""
import logging
from pathlib import Path
from typing import Optional, Tuple

import fitz  # PyMuPDF
from docx import Document as DocxDocument
# from markdownify import markdownify as md # No longer converting to Markdown here

from ..models.document_models import DocumentStatus

# Setup logger
logger = logging.getLogger(__name__)

# Supported file types for text extraction
SUPPORTED_TEXT_EXTRACTION_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}

# Define supported image types for direct AI analysis
SUPPORTED_IMAGE_TYPES_FOR_AI = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

class DocumentProcessingService:
    def __init__(self):
        pass

    async def _extract_text_from_pdf(self, file_path: Path) -> str:
        """Extracts text from a PDF file and converts to Markdown."""
        try:
            logger.info(f"Attempting to extract text from PDF: {file_path}")
            # PyMuPDF4LLM offers direct to_markdown, which is ideal
            # For older PyMuPDF or more control, extract text then convert
            # md_text = fitz.open(file_path).convert_to_markdown() # Simplified if pymupdf4llm is used
            
            doc = fitz.open(file_path)
            text_content = ""
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text_content += page.get_text("text") + "\n\n" # Add double newline between pages
            doc.close()
            
            # Convert the combined text to Markdown if not already Markdown
            # For now, we assume get_text() gives plain text that's good enough,
            # or we can use a more sophisticated HTML to Markdown if get_text("html") was used.
            # markdown_content = md(text_content) 
            # Let's return plain text for now, Markdown conversion can be a refinement.
            logger.info(f"Successfully extracted text from PDF: {file_path}")
            return text_content.strip()
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {e}", exc_info=True)
            raise

    async def _extract_text_from_docx(self, file_path: Path) -> str:
        """Extracts text from a DOCX file."""
        try:
            logger.info(f"Attempting to extract text from DOCX: {file_path}")
            document = DocxDocument(file_path)
            full_text = [para.text for para in document.paragraphs]
            extracted_text = '\n'.join(full_text)
            # Consider converting to Markdown if formatting is important
            # markdown_content = md(extracted_text) # This might not work well if no HTML
            logger.info(f"Successfully extracted text from DOCX: {file_path}")
            return extracted_text.strip()
        except Exception as e:
            logger.error(f"Error extracting text from DOCX {file_path}: {e}", exc_info=True)
            raise

    async def _extract_text_from_txt(self, file_path: Path) -> str:
        """Extracts text from a TXT file."""
        try:
            logger.info(f"Attempting to extract text from TXT: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                text_content = f.read()
            logger.info(f"Successfully extracted text from TXT: {file_path}")
            return text_content.strip()
        except Exception as e:
            logger.error(f"Error extracting text from TXT {file_path}: {e}", exc_info=True)
            raise

    async def get_image_bytes(self, file_path_str: str) -> Optional[bytes]:
        """Reads and returns the bytes of an image file."""
        file_path = Path(file_path_str)
        if not file_path.exists():
            logger.error(f"Image file not found: {file_path_str}")
            return None
        
        file_ext = file_path.suffix.lower()
        if file_ext not in SUPPORTED_IMAGE_TYPES_FOR_AI:
            logger.warning(f"File {file_path_str} is not a supported image type for AI analysis.")
            return None
        
        try:
            with open(file_path, 'rb') as f:
                image_bytes = f.read()
            logger.info(f"Successfully read image bytes from: {file_path_str}")
            return image_bytes
        except Exception as e:
            logger.error(f"Error reading image file {file_path_str}: {e}", exc_info=True)
            return None

    async def extract_text_from_document(
        self, file_path_str: str, file_type: Optional[str]
    ) -> Tuple[Optional[str], DocumentStatus, Optional[str]]:
        """
        Extracts text from a document based on its file type.

        Args:
            file_path_str: The string path to the document file.
            file_type: The MIME type of the file.

        Returns:
            A tuple containing:
            - extracted_text (Optional[str]): The extracted text, or None if extraction failed or not supported.
            - new_status (DocumentStatus): The new status for the document.
            - error_message (Optional[str]): An error message if extraction failed.
        """
        file_path = Path(file_path_str)
        extracted_text: Optional[str] = None
        error_message: Optional[str] = None
        
        if not file_path.exists():
            logger.error(f"File not found for extraction: {file_path_str}")
            return None, DocumentStatus.PROCESSING_ERROR, "File not found for extraction."

        file_ext = file_path.suffix.lower()
        
        try:
            if file_type == SUPPORTED_TEXT_EXTRACTION_TYPES.get(".pdf") or file_ext == ".pdf":
                extracted_text = await self._extract_text_from_pdf(file_path)
            elif file_type == SUPPORTED_TEXT_EXTRACTION_TYPES.get(".docx") or file_ext == ".docx":
                extracted_text = await self._extract_text_from_docx(file_path)
            elif file_type == SUPPORTED_TEXT_EXTRACTION_TYPES.get(".txt") or file_ext == ".txt":
                extracted_text = await self._extract_text_from_txt(file_path)
            # Check if it's a supported image type for AI (but not for text extraction here)
            elif file_ext in SUPPORTED_IMAGE_TYPES_FOR_AI or file_type in SUPPORTED_IMAGE_TYPES_FOR_AI.values():
                logger.info(f"File {file_path_str} is an image. Text extraction is not applicable directly. Will be handled by AI service.")
                # For images, text extraction is not done here. Status remains UPLOADED or similar until AI processing.
                # The caller will decide to use get_image_bytes and then call AI.
                return None, DocumentStatus.UPLOADED, "Image file, text extraction not applicable via this method."
            else:
                logger.warning(f"Unsupported file type for text extraction: {file_type} (path: {file_path_str})")
                return None, DocumentStatus.UPLOADED, f"Unsupported file type: {file_type or file_ext}"

            if extracted_text is not None:
                logger.info(f"Text extraction successful for {file_path_str}. Length: {len(extracted_text)}")
                return extracted_text, DocumentStatus.TEXT_EXTRACTED, None
            else: # Should not happen if no exception, but as a safeguard
                logger.error(f"Text extraction resulted in None for {file_path_str} without explicit error.")
                return None, DocumentStatus.PROCESSING_ERROR, "Text extraction failed with no specific error message."

        except Exception as e:
            logger.error(f"Failed to extract text from {file_path_str}: {e}", exc_info=True)
            error_message = f"Text extraction failed: {str(e)}"
            return None, DocumentStatus.PROCESSING_ERROR, error_message

# Example usage (for testing or direct calls if needed)
# async def main():
#     service = DocumentProcessingService()
#     # Create dummy files for testing
#     # pdf_text, pdf_status, pdf_err = await service.extract_text_from_document("path/to/your.pdf", "application/pdf")
#     # print(f"PDF: Status - {pdf_status}, Error - {pdf_err}, Text: {pdf_text[:200]}...")
#
# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main()) 