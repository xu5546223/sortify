"""
Service for processing uploaded documents, including text extraction
and potentially other pre-processing steps before AI analysis.
"""
import logging
from pathlib import Path
from typing import Optional, Tuple

import fitz  # PyMuPDF
from docx import Document as DocxDocument

from ...models.document_models import DocumentStatus

from ...core.logging_utils import log_event, LogLevel # Added
from ...models.document_models import Document # For type hinting if needed by log_event context, though not directly used now

# Setup logger
logger = logging.getLogger(__name__) # Existing logger can remain for very fine-grained internal logs

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
        """Extracts text from a PDF file."""
        await log_event(db=None, level=LogLevel.DEBUG, message="Attempting PDF text extraction.",
                        source="service.doc_processing.pdf_extractor", details={"file_path": str(file_path)})
        try:
            doc = fitz.open(file_path)
            text_content = ""
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text_content += page.get_text("text") + "\n\n"
            doc.close()
            await log_event(db=None, level=LogLevel.DEBUG, message="PDF text extraction successful.",
                            source="service.doc_processing.pdf_extractor", details={"file_path": str(file_path), "extracted_length": len(text_content)})
            return text_content.strip()
        except Exception as e:
            await log_event(db=None, level=LogLevel.ERROR, message=f"Error extracting text from PDF: {str(e)}",
                            source="service.doc_processing.pdf_extractor", exc_info=True,
                            details={"file_path": str(file_path), "error_type": type(e).__name__})
            raise

    async def _extract_text_from_docx(self, file_path: Path) -> str:
        """Extracts text from a DOCX file."""
        await log_event(db=None, level=LogLevel.DEBUG, message="Attempting DOCX text extraction.",
                        source="service.doc_processing.docx_extractor", details={"file_path": str(file_path)})
        try:
            document = DocxDocument(file_path)
            full_text = [para.text for para in document.paragraphs]
            extracted_text = '\n'.join(full_text)
            await log_event(db=None, level=LogLevel.DEBUG, message="DOCX text extraction successful.",
                            source="service.doc_processing.docx_extractor", details={"file_path": str(file_path), "extracted_length": len(extracted_text)})
            return extracted_text.strip()
        except Exception as e:
            await log_event(db=None, level=LogLevel.ERROR, message=f"Error extracting text from DOCX: {str(e)}",
                            source="service.doc_processing.docx_extractor", exc_info=True,
                            details={"file_path": str(file_path), "error_type": type(e).__name__})
            raise

    async def _extract_text_from_txt(self, file_path: Path) -> str:
        """Extracts text from a TXT file."""
        await log_event(db=None, level=LogLevel.DEBUG, message="Attempting TXT text extraction.",
                        source="service.doc_processing.txt_extractor", details={"file_path": str(file_path)})
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text_content = f.read()
            await log_event(db=None, level=LogLevel.DEBUG, message="TXT text extraction successful.",
                            source="service.doc_processing.txt_extractor", details={"file_path": str(file_path), "extracted_length": len(text_content)})
            return text_content.strip()
        except Exception as e:
            await log_event(db=None, level=LogLevel.ERROR, message=f"Error extracting text from TXT: {str(e)}",
                            source="service.doc_processing.txt_extractor", exc_info=True,
                            details={"file_path": str(file_path), "error_type": type(e).__name__})
            raise

    async def get_image_bytes(self, file_path_str: str) -> Optional[bytes]:
        """Reads and returns the bytes of an image file."""
        file_path = Path(file_path_str)
        log_details = {"file_path": file_path_str}
        await log_event(db=None, level=LogLevel.DEBUG, message="Attempting to read image bytes.",
                        source="service.doc_processing.get_image_bytes", details=log_details)

        if not file_path.exists():
            await log_event(db=None, level=LogLevel.ERROR, message="Image file not found.",
                            source="service.doc_processing.get_image_bytes", details=log_details)
            return None
        
        file_ext = file_path.suffix.lower()
        if file_ext not in SUPPORTED_IMAGE_TYPES_FOR_AI:
            await log_event(db=None, level=LogLevel.WARNING, message="Unsupported image type for AI analysis.",
                            source="service.doc_processing.get_image_bytes", details=log_details)
            return None
        
        try:
            with open(file_path, 'rb') as f:
                image_bytes = f.read()
            await log_event(db=None, level=LogLevel.DEBUG, message="Successfully read image bytes.",
                            source="service.doc_processing.get_image_bytes", details=log_details)
            return image_bytes
        except Exception as e:
            await log_event(db=None, level=LogLevel.ERROR, message=f"Error reading image file: {str(e)}",
                            source="service.doc_processing.get_image_bytes", exc_info=True,
                            details={"file_path": file_path_str, "error_type": type(e).__name__})
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
        # document_id and user_id are not available here, pass None or get them if service context changes
        # For now, db=None for log_event as this service layer might not have direct db access.
        # If this service is always called with a document context, consider passing document_id.
        log_details_initial = {"file_path": file_path_str, "declared_file_type": file_type}
        await log_event(db=None, level=LogLevel.INFO, message="Starting text extraction.",
                        source="service.doc_processing.extract_text", details=log_details_initial)

        file_path = Path(file_path_str)
        extracted_text: Optional[str] = None
        error_message: Optional[str] = None
        
        if not file_path.exists():
            error_message = "File not found for extraction."
            await log_event(db=None, level=LogLevel.ERROR, message=error_message,
                            source="service.doc_processing.extract_text", details=log_details_initial)
            return None, DocumentStatus.PROCESSING_ERROR, error_message

        file_ext = file_path.suffix.lower()
        
        try:
            if file_type == SUPPORTED_TEXT_EXTRACTION_TYPES.get(".pdf") or file_ext == ".pdf":
                extracted_text = await self._extract_text_from_pdf(file_path)
            elif file_type == SUPPORTED_TEXT_EXTRACTION_TYPES.get(".docx") or file_ext == ".docx":
                extracted_text = await self._extract_text_from_docx(file_path)
            elif file_type == SUPPORTED_TEXT_EXTRACTION_TYPES.get(".txt") or file_ext == ".txt":
                extracted_text = await self._extract_text_from_txt(file_path)
            elif file_ext in SUPPORTED_IMAGE_TYPES_FOR_AI or file_type in SUPPORTED_IMAGE_TYPES_FOR_AI.values():
                message = "Image file, text extraction not applicable via this method."
                await log_event(db=None, level=LogLevel.INFO, message=message,
                                source="service.doc_processing.extract_text", details=log_details_initial)
                return None, DocumentStatus.UPLOADED, message
            else:
                error_message = f"Unsupported file type for text extraction: {file_type or file_ext}"
                await log_event(db=None, level=LogLevel.WARNING, message=error_message,
                                source="service.doc_processing.extract_text", details=log_details_initial)
                return None, DocumentStatus.UPLOADED, error_message

            if extracted_text is not None:
                await log_event(db=None, level=LogLevel.INFO, message="Text extraction successful.",
                                source="service.doc_processing.extract_text",
                                details={"file_path": file_path_str, "extracted_length": len(extracted_text)})
                return extracted_text, DocumentStatus.TEXT_EXTRACTED, None
            else:
                error_message = "Text extraction resulted in None without explicit error."
                await log_event(db=None, level=LogLevel.ERROR, message=error_message,
                                source="service.doc_processing.extract_text", details=log_details_initial)
                return None, DocumentStatus.PROCESSING_ERROR, error_message

        except Exception as e:
            error_message = f"Text extraction failed: {str(e)}"
            await log_event(db=None, level=LogLevel.ERROR, message=error_message,
                            source="service.doc_processing.extract_text", exc_info=True, # exc_info for traceback in internal logs
                            details={"file_path": file_path_str, "error_type": type(e).__name__})
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