import React from 'react';

interface TableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  children: React.ReactNode;
}

const TableRow: React.FC<TableRowProps> = ({ children, className = '', ...props }) => {
  const defaultTrClass = 'hover:bg-surface-100'; // Apply hover effect by default
  return (
    <tr className={`${defaultTrClass} ${className}`}{...props}>
      {children}
    </tr>
  );
};

export default TableRow; 