// App.js
import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Route, Routes, Navigate } from 'react-router-dom';
import Login from './components/Login';
import Register from './components/Register';
import Chat from './components/Chat';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [token, setToken] = useState('');

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    if (storedToken) {
      setIsAuthenticated(true);
      setToken(storedToken);
    }
  }, []);

  const handleLogin = (newToken) => {
    setIsAuthenticated(true);
    setToken(newToken);
    localStorage.setItem('token', newToken);
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setToken('');
    localStorage.removeItem('token');
  };

  return (
    <Router>
      <div className="App">
        <Routes>
          <Route path="/" element={isAuthenticated ? <Navigate to="/chat" /> : <Navigate to="/login" />} />
          <Route path="/login" element={<Login onLogin={handleLogin} />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/chat"
            element={isAuthenticated ? <Chat token={token} onLogout={handleLogout} /> : <Navigate to="/login" />}
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;