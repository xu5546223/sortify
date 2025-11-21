import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { navItems } from '../../config/navConfig';

const Sidebar = React.memo(() => {
  const { logout, currentUser } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/auth/login');
  };

  // 導航項目分組
  const workspaceItems = navItems.filter(item => 
    ['/dashboard', '/documents', '/ai-qa'].includes(item.path)
  );
  
  const dataItems = navItems.filter(item => 
    ['/connection', '/vector-database', '/cache-monitoring'].includes(item.path)
  );
  
  const systemItems = navItems.filter(item => 
    ['/settings', '/logs', '/theme'].includes(item.path)
  );

  const renderNavItem = (item: typeof navItems[0]) => (
    <NavLink
      key={item.path}
      to={item.path}
      className={({ isActive }) =>
        `flex items-center gap-3 px-4 py-3 mb-1 font-bold rounded-lg border-2 transition-all cursor-pointer ${
          isActive
            ? 'bg-active text-white border-[var(--color-border)] shadow-[var(--shadow-md)]'
            : 'text-[var(--color-text)] border-transparent hover:bg-hover hover:border-[var(--color-border)] hover:shadow-[2px_2px_0px_0px_var(--shadow-color)] hover:-translate-x-[1px] hover:-translate-y-[1px]'
        }`
      }
    >
      <i className={`fas ${item.icon} text-xl`}></i>
      <span>{item.name}</span>
    </NavLink>
  );

  return (
    <aside className="fixed top-0 left-0 h-screen w-[280px] bg-[var(--color-card)] border-r-[3px] border-[var(--color-border)] flex flex-col transition-colors duration-300">
      {/* Logo Header */}
      <div className="p-6 flex flex-col items-center gap-2 border-b-[3px] border-[var(--color-border)] bg-[var(--color-card)]">
        <div className="w-12 h-12 bg-primary border-[3px] border-[var(--color-border)] shadow-[var(--shadow-md)] flex items-center justify-center text-white">
          <i className="fas fa-folder-open text-2xl"></i>
        </div>
        <h1 className="font-heading text-2xl font-black tracking-tight mt-1">
          SORTIFY
        </h1>
      </div>

      {/* Navigation - Scrollable */}
      <nav className="flex-1 overflow-y-auto p-4 scrollbar-hide">
        {/* Workspace Group */}
        <div className="mb-4">
          <div className="text-xs font-black uppercase text-[var(--color-text-sub)] px-4 py-2 tracking-wider">
            Workspace
          </div>
          {workspaceItems.map(renderNavItem)}
        </div>

        {/* Data & Monitor Group */}
        {dataItems.length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-black uppercase text-[var(--color-text-sub)] px-4 py-2 tracking-wider border-t-2 border-dashed border-[var(--color-text-sub)] mt-2 pt-4">
              Data & Monitor
            </div>
            {dataItems.map(renderNavItem)}
          </div>
        )}

        {/* System Group */}
        {systemItems.length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-black uppercase text-[var(--color-text-sub)] px-4 py-2 tracking-wider border-t-2 border-dashed border-[var(--color-text-sub)] mt-2 pt-4">
              System
            </div>
            {systemItems.map(renderNavItem)}
          </div>
        )}

        {/* All other items */}
        {navItems
          .filter(item => 
            !workspaceItems.includes(item) && 
            !dataItems.includes(item) && 
            !systemItems.includes(item)
          )
          .map(renderNavItem)}
      </nav>

      {/* User Profile Footer */}
      {currentUser && (
        <div className="p-4 border-t-[3px] border-[var(--color-border)] bg-[var(--color-bg)]">
          <div className="border-2 border-[var(--color-border)] bg-[var(--color-card)] p-3 shadow-[var(--shadow-sm)] flex items-center justify-between group transition-transform hover:-translate-y-1">
            <div className="flex items-center gap-3 overflow-hidden">
              {/* Avatar */}
              <div className="w-10 h-10 bg-[var(--color-text)] text-[var(--color-card)] flex-shrink-0 flex items-center justify-center font-black border border-[var(--color-border)] text-sm">
                {currentUser.username.substring(0, 2).toUpperCase()}
              </div>
              <div className="flex flex-col min-w-0">
                <span className="font-bold text-sm truncate text-[var(--color-text)]">
                  {currentUser.username}
                </span>
                <span className="text-xs text-[var(--color-text-sub)] truncate font-medium">
                  {currentUser.email || 'Admin'}
                </span>
              </div>
            </div>

            {/* Logout Button */}
            <button
              onClick={handleLogout}
              className="w-8 h-8 rounded flex items-center justify-center transition-colors hover:text-error hover:bg-red-100 text-[var(--color-text)]"
              title="登出"
            >
              <i className="fas fa-sign-out-alt text-lg"></i>
            </button>
          </div>
        </div>
      )}
    </aside>
  );
});

export default Sidebar;