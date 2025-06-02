import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import LoadingIndicator from '../common/LoadingIndicator';

interface PublicRouteWrapperProps {
  children: JSX.Element;
}

const PublicRouteWrapper: React.FC<PublicRouteWrapperProps> = ({ children }) => {
  const { currentUser, isLoading } = useAuth();
  if (isLoading) return <LoadingIndicator />;
  return !currentUser ? children : <Navigate to="/dashboard" replace />;
};

export default PublicRouteWrapper; 