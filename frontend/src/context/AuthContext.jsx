import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from 'react';
import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserAttribute,
  CognitoRefreshToken,
} from 'amazon-cognito-identity-js';
import { configureApi } from '../services/api';

const poolData = {
  UserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || '',
  ClientId: import.meta.env.VITE_COGNITO_APP_CLIENT_ID || '',
};

const userPool = new CognitoUserPool(poolData);

const AuthContext = createContext(null);

const REFRESH_TOKEN_KEY = 'awaas_refresh_token';
const USERNAME_KEY = 'awaas_username';

function decodeIdToken(idToken) {
  try {
    const payload = idToken.split('.')[1];
    const decoded = JSON.parse(atob(payload));
    return { sub: decoded.sub, email: decoded.email };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [accessToken, setAccessToken] = useState(null);
  const [idToken, setIdToken] = useState(null);
  const [refreshToken, setRefreshToken] = useState(null);

  const clearAuth = useCallback(() => {
    setUser(null);
    setIsAuthenticated(false);
    setAccessToken(null);
    setIdToken(null);
    setRefreshToken(null);
    sessionStorage.removeItem(REFRESH_TOKEN_KEY);
    sessionStorage.removeItem(USERNAME_KEY);
  }, []);

  const storeTokens = useCallback((session) => {
    const access = session.getAccessToken().getJwtToken();
    const id = session.getIdToken().getJwtToken();
    const refresh = session.getRefreshToken().getToken();

    setAccessToken(access);
    setIdToken(id);
    setRefreshToken(refresh);
    sessionStorage.setItem(REFRESH_TOKEN_KEY, refresh);

    const userInfo = decodeIdToken(id);
    if (userInfo) {
      setUser(userInfo);
      setIsAuthenticated(true);
    }
  }, []);

  const refreshSession = useCallback(() => {
    return new Promise((resolve, reject) => {
      const storedRefreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY);
      const storedUsername = sessionStorage.getItem(USERNAME_KEY);

      if (!storedRefreshToken || !storedUsername) {
        reject(new Error('No refresh token available'));
        return;
      }

      const cognitoUser = new CognitoUser({
        Username: storedUsername,
        Pool: userPool,
      });

      const token = new CognitoRefreshToken({ RefreshToken: storedRefreshToken });

      cognitoUser.refreshSession(token, (err, session) => {
        if (err) {
          clearAuth();
          reject(err);
          return;
        }
        storeTokens(session);
        resolve(session);
      });
    });
  }, [clearAuth, storeTokens]);

  // Keep a ref to access token so configureApi always gets the latest value
  const accessTokenRef = useRef(accessToken);
  accessTokenRef.current = accessToken;

  // Configure API module with auth callbacks
  useEffect(() => {
    configureApi({
      getAccessToken: () => accessTokenRef.current,
      refreshSession,
      logout: () => {
        clearAuth();
        window.location.href = '/login';
      },
    });
  }, [refreshSession, clearAuth]);

  // Silent token refresh on mount
  useEffect(() => {
    let cancelled = false;
    const storedRefreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY);
    const storedUsername = sessionStorage.getItem(USERNAME_KEY);

    if (storedRefreshToken && storedUsername) {
      refreshSession()
        .catch(() => {
          if (!cancelled) clearAuth();
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    } else {
      // Use microtask to avoid synchronous setState in effect body
      Promise.resolve().then(() => {
        if (!cancelled) setIsLoading(false);
      });
    }

    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback((email, password) => {
    return new Promise((resolve, reject) => {
      const authDetails = new AuthenticationDetails({
        Username: email,
        Password: password,
      });

      const cognitoUser = new CognitoUser({
        Username: email,
        Pool: userPool,
      });

      cognitoUser.authenticateUser(authDetails, {
        onSuccess: (session) => {
          sessionStorage.setItem(USERNAME_KEY, email);
          storeTokens(session);
          resolve(session);
        },
        onFailure: (err) => {
          reject(err);
        },
      });
    });
  }, [storeTokens]);

  const signup = useCallback((email, password) => {
    return new Promise((resolve, reject) => {
      const attributeList = [
        new CognitoUserAttribute({ Name: 'email', Value: email }),
      ];

      userPool.signUp(email, password, attributeList, null, (err, result) => {
        if (err) {
          reject(err);
          return;
        }
        resolve(result);
      });
    });
  }, []);

  const confirmSignup = useCallback((email, code) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({
        Username: email,
        Pool: userPool,
      });

      cognitoUser.confirmRegistration(code, true, (err, result) => {
        if (err) {
          reject(err);
          return;
        }
        resolve(result);
      });
    });
  }, []);

  const forgotPassword = useCallback((email) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({
        Username: email,
        Pool: userPool,
      });

      cognitoUser.forgotPassword({
        onSuccess: (data) => {
          resolve(data);
        },
        onFailure: (err) => {
          reject(err);
        },
      });
    });
  }, []);

  const resetPassword = useCallback((email, code, newPassword) => {
    return new Promise((resolve, reject) => {
      const cognitoUser = new CognitoUser({
        Username: email,
        Pool: userPool,
      });

      cognitoUser.confirmPassword(code, newPassword, {
        onSuccess: () => {
          resolve();
        },
        onFailure: (err) => {
          reject(err);
        },
      });
    });
  }, []);

  const logout = useCallback(() => {
    const storedUsername = sessionStorage.getItem(USERNAME_KEY);
    if (storedUsername) {
      const cognitoUser = new CognitoUser({
        Username: storedUsername,
        Pool: userPool,
      });
      cognitoUser.signOut();
    }
    clearAuth();
    window.location.href = '/login';
  }, [clearAuth]);

  const value = {
    user,
    isAuthenticated,
    isLoading,
    accessToken,
    idToken,
    refreshToken,
    login,
    signup,
    confirmSignup,
    forgotPassword,
    resetPassword,
    logout,
    refreshSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
