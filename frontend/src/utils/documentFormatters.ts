export const formatBytes = (bytes?: number, decimals = 2): string => {
  if (bytes === undefined || bytes === null || bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
};

export const formatDate = (dateString?: string): string => {
  if (!dateString) return 'N/A';
  try {
    let adjustedDateString = dateString;
    if (dateString.includes('T') && !dateString.endsWith('Z') && dateString.length >= 19) {
      adjustedDateString = dateString + 'Z';
    }
    const dateObj = new Date(adjustedDateString);
    return dateObj.toLocaleString('zh-TW', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  } catch (e) {
    console.error("Error formatting date:", dateString, e);
    return dateString;
  }
};

export const mapMimeTypeToSimpleType = (mimeType?: string | null): string => {
  if (!mimeType) return '未知類型';

  const lowerMimeType = mimeType.toLowerCase();

  // 精確匹配
  if (lowerMimeType === 'application/pdf') return 'PDF 文件';
  if (lowerMimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') return 'Word 文件 (DOCX)';
  if (lowerMimeType === 'application/msword') return 'Word 文件 (DOC)';
  if (lowerMimeType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') return 'Excel 文件 (XLSX)';
  if (lowerMimeType === 'application/vnd.ms-excel') return 'Excel 文件 (XLS)';
  if (lowerMimeType === 'application/vnd.openxmlformats-officedocument.presentationml.presentation') return 'PowerPoint 文件 (PPTX)';
  if (lowerMimeType === 'application/vnd.ms-powerpoint') return 'PowerPoint 文件 (PPT)';
  if (lowerMimeType === 'application/zip') return 'ZIP 壓縮檔';
  if (lowerMimeType === 'application/json') return 'JSON 文件';
  if (lowerMimeType === 'application/xml') return 'XML 文件';

  // 前綴匹配
  if (lowerMimeType.startsWith('text/plain')) return '純文字文件';
  if (lowerMimeType.startsWith('text/')) return '文字文件';
  if (lowerMimeType.startsWith('image/jpeg')) return 'JPEG 圖片';
  if (lowerMimeType.startsWith('image/png')) return 'PNG 圖片';
  if (lowerMimeType.startsWith('image/gif')) return 'GIF 圖片';
  if (lowerMimeType.startsWith('image/svg+xml')) return 'SVG 圖片';
  if (lowerMimeType.startsWith('image/')) return '圖片';
  if (lowerMimeType.startsWith('audio/')) return '音訊檔案';
  if (lowerMimeType.startsWith('video/')) return '影片檔案';

  return mimeType;
};

