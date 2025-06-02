import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import LoadingIndicator from '../common/LoadingIndicator';

interface ProtectedRouteWrapperProps {
  children: JSX.Element;
}

const ProtectedRouteWrapper: React.FC<ProtectedRouteWrapperProps> = ({ children }) => {
  const { currentUser, isLoading } = useAuth();
  if (isLoading) return <LoadingIndicator />;
  return currentUser ? children : <Navigate to="/auth/login" replace />;
};

export default ProtectedRouteWrapper; 