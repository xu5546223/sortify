import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { navItems } from '../../config/navConfig'; // 導入 navItems

// Icon helper function (specific to Sidebar)
const icon = (className: string): JSX.Element => <i className={`fas ${className} fa-fw mr-2`}></i>;

const Sidebar = React.memo(() => {
  const { logout, currentUser } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/auth/login');
  };

  return (
    <div className="sidebar fixed top-0 left-0 h-full overflow-y-auto bg-surface-900 text-surface-100 w-64 flex flex-col">
      <div className="logo p-5 text-center border-b border-surface-700 flex flex-col items-center justify-center">
        <img 
          src="/images/logo.png" 
          alt="Sortify Logo" 
          className="w-12 h-auto mb-3 object-contain"
        />
        <span className="text-lg font-semibold text-white">Sortify</span>
      </div>
      
      <nav className="flex-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `block py-3 px-5 text-surface-300 hover:bg-surface-800 hover:text-white transition-colors duration-200 border-l-4 border-transparent ${
                isActive ? "bg-surface-800 text-white border-primary-500" : ""
              }`
            }
          >
            {icon(item.icon)}{item.name}
          </NavLink>
        ))}
      </nav>

      {/* 用戶信息和登出按鈕 */}
      <div className="border-t border-surface-700 mt-auto">
        {currentUser && (
          <div className="p-4 text-surface-300 text-sm border-b border-surface-700">
            <div className="flex items-center space-x-2 mb-1">
              <i className="fas fa-user fa-fw"></i>
              <span className="font-medium text-white truncate">{currentUser.username}</span>
            </div>
            {currentUser.email && (
              <div className="text-xs text-surface-400 truncate ml-6">
                {currentUser.email}
              </div>
            )}
          </div>
        )}
        
        <button
          onClick={handleLogout}
          className="w-full py-3 px-5 text-surface-300 hover:bg-red-600 hover:text-white transition-colors duration-200 text-left flex items-center"
        >
          <i className="fas fa-sign-out-alt fa-fw mr-2"></i>
          <span>登出系統</span>
        </button>
      </div>
    </div>
  );
});

export default Sidebar; 