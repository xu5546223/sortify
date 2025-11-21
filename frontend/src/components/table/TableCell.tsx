import React from 'react';

interface TableCellProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  children: React.ReactNode;
}

const TableCell: React.FC<TableCellProps> = ({ children, className = '', ...props }) => {
  const defaultTdClass = 'px-3 py-3';
  
  // 如果 className 包含 'relative' 或 'overflow'，添加特殊樣式確保下拉菜單不被裁剪
  const hasOverflowHandling = className.includes('relative') || className.includes('overflow');
  const finalClass = hasOverflowHandling 
    ? `${defaultTdClass} ${className}` 
    : `${defaultTdClass} ${className}`;
  
  return (
    <td className={finalClass} {...props}>
      {children}
    </td>
  );
};

export default TableCell;