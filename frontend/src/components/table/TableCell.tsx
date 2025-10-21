import React from 'react';

interface TableCellProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  children: React.ReactNode;
}

const TableCell: React.FC<TableCellProps> = ({ children, className = '', ...props }) => {
  const defaultTdClass = 'px-6 py-4 text-sm text-surface-900';
  return (
    <td className={`${defaultTdClass} ${className}`} {...props}>
      {children}
    </td>
  );
};

export default TableCell; 