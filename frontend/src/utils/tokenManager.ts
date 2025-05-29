export class TokenManager {
  private static TOKEN_KEY = 'authToken';
  
  static setToken(token: string): void {
    localStorage.setItem(this.TOKEN_KEY, token);
  }
  
  static getToken(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }
  
  static removeToken(): void {
    localStorage.removeItem(this.TOKEN_KEY);
  }
  
  static isTokenValid(): boolean {
    const token = this.getToken();
    if (!token) return false;
    
    try {
      // Basic check for JWT structure (header.payload.signature)
      const parts = token.split('.');
      if (parts.length !== 3) return false;

      const payload = JSON.parse(atob(parts[1]));
      // Check if 'exp' (expiration time) claim exists and is in the future
      return payload.exp && payload.exp > Date.now() / 1000;
    } catch (error) {
      // If parsing fails or payload is not as expected, token is invalid
      console.error("Token validation error:", error);
      return false;
    }
  }
  
  static isTokenExpiringSoon(minutesThreshold = 5): boolean {
    const token = this.getToken();
    if (!token) return true; // If no token, consider it as needing refresh/login
    
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return true; // Invalid token structure

      const payload = JSON.parse(atob(parts[1]));
      if (!payload.exp) return true; // No expiration claim

      const expirationTime = payload.exp * 1000; // Convert to milliseconds
      const currentTime = Date.now();
      const threshold = minutesThreshold * 60 * 1000; // Convert minutes to milliseconds
      
      return (expirationTime - currentTime) < threshold;
    } catch (error) {
      console.error("Token expiration check error:", error);
      return true; // If any error, assume it might be expiring or invalid
    }
  }
} 