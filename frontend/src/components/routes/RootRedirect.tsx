import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import LoadingIndicator from '../common/LoadingIndicator';

const RootRedirect: React.FC = () => {
  const { currentUser, isLoading } = useAuth();
  if (isLoading) return <LoadingIndicator />;
  return currentUser ? <Navigate to="/dashboard" replace /> : <Navigate to="/auth/login" replace />;
};

export default RootRedirect; 