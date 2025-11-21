import React, { useState, useEffect, useRef } from 'react';
import { Card, Button, Input } from '../ui'; // Updated import path
import type { Document as DocumentType } from '../../types/apiTypes'; // Updated import path
import { apiClient } from '../../services/apiClient'; // Updated import path
import { Document, Page, pdfjs } from 'react-pdf';
import { formatBytes } from '../../utils/documentFormatters'; // Updated import path

import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface PreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  doc: DocumentType | null;
}

const PreviewModal: React.FC<PreviewModalProps> = ({ isOpen, onClose, doc }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [pdfFile, setPdfFile] = useState<string | Blob | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const imageContainerRef = useRef<HTMLDivElement>(null); 
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState<number>(1);
  const [pdfPageInput, setPdfPageInput] = useState<string>("1");

  useEffect(() => {
    setPdfPageInput(String(pageNumber));
  }, [pageNumber]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isOpen) return;
      switch (event.key) {
        case 'Escape':
          onClose();
          break;
        case 'ArrowLeft':
          if (numPages > 0 && pageNumber > 1) {
            setPageNumber(prev => prev - 1);
          }
          break;
        case 'ArrowRight':
          if (numPages > 0 && pageNumber < numPages) {
            setPageNumber(prev => prev + 1);
          }
          break;
      }
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose, numPages, pageNumber]);

  useEffect(() => {
    setImageSrc(null);
    setPdfFile(null); 
    setPreviewError(null);
    setNumPages(0);
    setPageNumber(1);

    if (isOpen && doc) {
      const fileType = doc.file_type?.toLowerCase() || '';
      const isImage = fileType.startsWith('image/');
      const isPdf = fileType === 'application/pdf';

      if (isImage) {
        let current = true;
        apiClient.get(`/documents/${doc.id}/file`, { responseType: 'blob' })
          .then(response => {
            if (current) {
              const objectUrl = URL.createObjectURL(response.data);
              setImageSrc(objectUrl);
            }
          })
          .catch(err => {
            if (current) {
              console.error('Error fetching image preview:', err);
              setPreviewError(`無法載入圖片預覽: ${doc.filename}. 錯誤: ${err.message || '未知錯誤'}`);
            }
          });
        return () => { current = false; }; 
      } else if (isPdf) {
        let current = true;
        apiClient.get(`/documents/${doc.id}/file`, { responseType: 'blob' })
          .then(response => {
            if (current) {
              if (response.data.type === 'application/pdf'){
                setPdfFile(response.data);
              } else {
                console.error('Fetched data is not a PDF for doc:', doc.filename);
                setPreviewError(`預覽失敗: ${doc.filename} 的文件內容非預期的PDF格式。`);
              }
            }
          })
          .catch(err => {
            if (current) {
              console.error('Error fetching PDF preview:', err);
              setPreviewError(`無法載入PDF檔案: ${doc.filename}. 錯誤: ${err.message || '未知錯誤'}`);
            }
          });
        return () => { current = false; }; 
      }
    }
  }, [isOpen, doc]);

  useEffect(() => {
    return () => {
      if (imageSrc) URL.revokeObjectURL(imageSrc);
    };
  }, [imageSrc]);

  if (!isOpen || !doc) return null;

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  function onDocumentLoadSuccess({ numPages: loadedNumPages }: { numPages: number }): void {
    setNumPages(loadedNumPages);
    setPageNumber(1);
  }

  function onDocumentLoadError(error: Error): void {
    console.error('Error while loading PDF document:', error);
    setPreviewError(`載入PDF時發生錯誤: ${error.message}`);
  }

  const goToPrevPage = () => setPageNumber(prevPageNumber => Math.max(prevPageNumber - 1, 1));
  const goToNextPage = () => setPageNumber(prevPageNumber => Math.min(prevPageNumber + 1, numPages));

  const handlePageInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPdfPageInput(e.target.value);
  };

  const handlePageInputSubmit = (e: React.FormEvent<HTMLFormElement> | React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    const newPageNum = parseInt(pdfPageInput, 10);
    if (!isNaN(newPageNum) && newPageNum >= 1 && newPageNum <= numPages) {
      setPageNumber(newPageNum);
    } else {
      setPdfPageInput(String(pageNumber));
    }
  };

  const fileType = doc.file_type?.toLowerCase() || '';
  const hasExtractedText = !!doc.extracted_text;
  const isTextPreviewable = hasExtractedText && (fileType.startsWith('text/') || fileType === 'application/json' || !fileType);

  let canDisplayImage = !!imageSrc;
  let canDisplayPdf = !!pdfFile;
  if (previewError) {
    canDisplayImage = false;
    canDisplayPdf = false;
  }

  const pdfLoadingMessage = <p className="text-center p-4">正在載入 PDF...</p>;
  const pdfErrorMessage = (message: string) => <p className="text-red-500 text-center p-4">{message}</p>;

  return (
    <div
      className="fixed inset-0 bg-black/90 flex items-center justify-center p-4 z-50"
      onClick={handleOverlayClick}
    >
      <div 
        onClick={(e: React.MouseEvent) => e.stopPropagation()} 
        className="relative w-full h-full max-w-7xl max-h-[95vh] bg-white rounded-lg shadow-2xl flex flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between p-4 border-b border-surface-200 bg-surface-50 rounded-t-lg flex-shrink-0">
          <h2 className="text-xl font-semibold text-surface-900 truncate">
            預覽: {doc.filename}
          </h2>
          <Button 
            onClick={onClose}
            variant="secondary"
            size="sm"
            className="ml-4 flex-shrink-0"
            aria-label="關閉預覽"
          >
            <i className="fas fa-times"></i>
          </Button>
        </div>

        <div className="flex-grow overflow-hidden flex flex-col min-h-0">
          {previewError && !pdfFile && (
            <div className="flex items-center justify-center h-full p-8">
              <p className="text-red-500 text-center text-lg">{previewError}</p>
            </div>
          )}
          
          {canDisplayImage && (
            <div className="flex-grow flex items-center justify-center p-4 overflow-hidden">
              <div className="max-w-full max-h-full flex items-center justify-center">
                <img
                  src={imageSrc || undefined} 
                  alt={`預覽 ${doc.filename}`}
                  className="max-w-full max-h-full object-contain rounded-lg shadow-sm"
                  style={{
                    maxHeight: 'calc(95vh - 120px)',
                    maxWidth: '100%'
                  }}
                />
              </div>
            </div>
          )}

          {canDisplayPdf && (
            <div className="flex-grow flex flex-col overflow-hidden">
              <div className="flex justify-center items-center space-x-2 py-3 px-4 border-b border-surface-200 bg-surface-100 flex-shrink-0">
                <Button onClick={goToPrevPage} disabled={pageNumber <= 1} variant="outline" size="sm">
                  <i className="fas fa-arrow-left mr-1"></i>上一頁
                </Button>
                <form onSubmit={handlePageInputSubmit} className="flex items-center space-x-1">
                  <span className="text-sm">第</span>
                  <Input 
                    type="text" 
                    value={pdfPageInput} 
                    onChange={handlePageInputChange} 
                    className="w-12 text-center p-1 border rounded text-sm" 
                    aria-label="目前頁碼"
                    fullWidth={false}
                  /> 
                  <span className="text-sm">/ {numPages || '-'} 頁</span>
                </form>
                <Button onClick={goToNextPage} disabled={pageNumber >= numPages} variant="outline" size="sm">
                  下一頁<i className="fas fa-arrow-right ml-1"></i>
                </Button>
              </div>
              
              <div className="flex-grow overflow-auto bg-surface-100 p-4 flex justify-center">
                <Document
                  file={pdfFile}
                  onLoadSuccess={onDocumentLoadSuccess}
                  onLoadError={onDocumentLoadError}
                  loading={pdfLoadingMessage}
                  error={pdfErrorMessage('載入 PDF 失敗，請確認文件是否正確。')}
                  className="flex justify-center"
                >
                  <Page 
                    pageNumber={pageNumber} 
                    renderTextLayer={true} 
                    renderAnnotationLayer={true}
                    className="shadow-lg rounded-lg"
                    scale={1}
                  />
                </Document>
              </div>
            </div>
          )}
          
          {isTextPreviewable && !canDisplayImage && !canDisplayPdf && (
            <div className="flex-grow overflow-auto p-4">
              <pre className="whitespace-pre-wrap text-sm bg-surface-100 p-4 rounded-lg border border-surface-200 font-mono text-surface-900">
                {doc.extracted_text}
              </pre>
            </div>
          )}
          
          {!previewError && !canDisplayImage && !canDisplayPdf && !isTextPreviewable && (
            <div className="flex-grow flex items-center justify-center p-8">
              <div className="text-center">
                <i className="fas fa-file-alt text-4xl text-surface-400 mb-4"></i>
                <p className="text-surface-600 text-lg">
                  此文件類型 ({fileType || '未知'}) 無法預覽，或沒有可顯示的內容。
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-surface-200 bg-surface-100 p-4 flex justify-between items-center flex-shrink-0 rounded-b-lg">
          <div className="text-sm text-surface-600">
            檔案大小: {doc.size ? formatBytes(doc.size) : '未知'}
          </div>
          <div className="flex space-x-2">
            <Button onClick={onClose} variant="primary">
              關閉
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PreviewModal; 