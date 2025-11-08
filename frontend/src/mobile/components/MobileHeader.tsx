import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeftOutlined, MenuOutlined } from '@ant-design/icons';

interface MobileHeaderProps {
  title: string;
  showBack?: boolean;
  showMenu?: boolean;
  onBack?: () => void;
  onMenuClick?: () => void;
  rightAction?: React.ReactNode;
}

const MobileHeader: React.FC<MobileHeaderProps> = ({
  title,
  showBack = false,
  showMenu = false,
  onBack,
  onMenuClick,
  rightAction
}) => {
  const navigate = useNavigate();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      navigate(-1);
    }
  };

  return (
    <div className="mobile-header">
      <div className="mobile-header-left">
        {showBack && (
          <ArrowLeftOutlined 
            className="mobile-header-icon" 
            onClick={handleBack}
          />
        )}
        {showMenu && (
          <MenuOutlined 
            className="mobile-header-icon" 
            onClick={onMenuClick}
          />
        )}
      </div>
      
      <h1 className="mobile-header-title">{title}</h1>
      
      <div className="mobile-header-right">
        {rightAction}
      </div>
    </div>
  );
};

export default MobileHeader;

