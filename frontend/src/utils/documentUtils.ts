// Helper function to determine if a document can be previewed
export const canPreview = (doc: { file_type?: string | null; extracted_text?: string | null }): boolean => {
  const fileType = doc.file_type?.toLowerCase() || '';
  const isImage = fileType.startsWith('image/');
  const isPdf = fileType === 'application/pdf';
  const hasExtractedText = !!doc.extracted_text;
  // For text, we check if extracted_text is available and if the type is suitable (text/*, json, or unknown)
  const isTextPreviewable = hasExtractedText && (fileType.startsWith('text/') || fileType === 'application/json' || !fileType);
  return isImage || isPdf || isTextPreviewable;
}; 