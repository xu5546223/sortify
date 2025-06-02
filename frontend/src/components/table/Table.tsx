import React from 'react';
import Checkbox from '../ui/Checkbox'; // Corrected import for default export

// New interface for richer header configuration
export interface HeaderConfig {
  key: string; 
  label: React.ReactNode;
  sortable?: boolean;
  onSort?: (key: string) => void; // Optional: Table component can call this when a sortable header is clicked
  className?: string; // Custom class for this specific <th>
}

interface TableProps {
  headers: string[] | HeaderConfig[]; // Accepts both old string array and new config array
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  thClassName?: string;
  tbodyClassName?: string;

  // Props for "Select All" checkbox functionality in the header (if a header has key 'selector')
  isSelectAllChecked?: boolean;
  onSelectAllChange?: (event: React.ChangeEvent<HTMLInputElement>) => void;
  isSelectAllDisabled?: boolean;

  // Props for displaying sort indicators based on external sort state
  sortConfig?: { key: string; direction: 'asc' | 'desc' } | null;
}

const Table: React.FC<TableProps> = ({
  headers,
  children,
  className = '',
  headerClassName = '',
  thClassName = '',
  tbodyClassName = '',
  isSelectAllChecked = false,
  onSelectAllChange,
  isSelectAllDisabled = false,
  sortConfig,
}) => {
  const defaultTableClass = 'min-w-full divide-y divide-gray-200 shadow-md rounded-lg overflow-hidden';
  const defaultTheadClass = 'bg-surface-100';
  const defaultThBaseClass = 'px-6 py-3 text-left text-xs font-medium text-surface-700 uppercase tracking-wider';
  const defaultTbodyClass = 'bg-surface-50 divide-y divide-surface-200';

  const renderHeaderContent = (headerOrConfig: string | HeaderConfig) => {
    // If it's a simple string header (backward compatibility)
    if (typeof headerOrConfig === 'string') {
      return headerOrConfig;
    }

    // If it's a HeaderConfig object
    const config = headerOrConfig;
    let labelContent = config.label;

    // Special handling for 'selector' key to render "Select All" checkbox
    if (config.key === 'selector' && onSelectAllChange) {
      return (
        <Checkbox
          id={`table-select-all-${config.key}`} // Make ID more specific
          checked={isSelectAllChecked}
          onChange={onSelectAllChange}
          disabled={isSelectAllDisabled}
        />
      );
    }

    // Add sort indicators if the column is sortable and current sortConfig matches
    if (config.sortable && sortConfig && sortConfig.key === config.key) {
      labelContent = (
        <>
          {config.label}
          {sortConfig.direction === 'asc' ? 
            <i className="fas fa-arrow-up ml-1 text-xs"></i> : 
            <i className="fas fa-arrow-down ml-1 text-xs"></i>
          }
        </>
      );
    }
    return labelContent;
  };

  return (
    <div className="overflow-x-auto">
      <table className={`${defaultTableClass} ${className}`}>
        <thead className={`${defaultTheadClass} ${headerClassName}`}>
          <tr>
            {headers.map((headerOrConfig, index) => {
              const isConfig = typeof headerOrConfig !== 'string';
              const key = isConfig ? headerOrConfig.key : `header-text-${index}`;
              const config = isConfig ? headerOrConfig : null;

              const thClasses = [
                defaultThBaseClass,
                config?.className || '',
                (config?.sortable ? 'cursor-pointer hover:bg-surface-100' : ''),
              ].filter(Boolean).join(' ');

              // If it's a config object and has onSort, use it, otherwise no onClick
              const handleClick = (config?.sortable && config.onSort) 
                ? () => config.onSort!(config.key) 
                : undefined;

              return (
                <th 
                  key={key} 
                  scope="col" 
                  className={thClasses}
                  onClick={handleClick}
                >
                  {renderHeaderContent(headerOrConfig)}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className={`${defaultTbodyClass} ${tbodyClassName}`}>
          {children}
        </tbody>
      </table>
    </div>
  );
};

export default Table; 