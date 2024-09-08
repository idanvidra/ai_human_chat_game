// components/Chat.js
import React, { useState, useEffect, useRef } from 'react';

function Chat({ token, onLogout }) {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [websocket, setWebsocket] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [partner, setPartner] = useState(null);
  const [status, setStatus] = useState('Waiting for partner...');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/${token}`);
    
    ws.onopen = () => {
      console.log('WebSocket Connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch(data.type) {
        case 'session_start':
          setSessionId(data.session_id);
          setPartner(data.partner);
          setStatus('Connected');
          break;
        case 'chat_message':
          setMessages(prevMessages => [...prevMessages, { user: data.user, content: data.message }]);
          break;
        case 'session_end':
          setStatus('Session ended. Waiting for new partner...');
          setSessionId(null);
          setPartner(null);
          setMessages([]);
          break;
        default:
          console.log('Unknown message type:', data.type);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket Disconnected');
      setStatus('Disconnected');
    };

    setWebsocket(ws);

    return () => {
      ws.close();
    };
  }, [token]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = (e) => {
    e.preventDefault();
    if (inputMessage && websocket && sessionId) {
      const message = {
        type: 'chat_message',
        session_id: sessionId,
        content: inputMessage
      };
      websocket.send(JSON.stringify(message));
      setInputMessage('');
    }
  };

  const endSession = () => {
    if (websocket && sessionId) {
      const message = {
        type: 'end_session',
        session_id: sessionId
      };
      websocket.send(JSON.stringify(message));
    }
  };

  return (
    <div>
      <h2>Chat Room</h2>
      <p>Status: {status}</p>
      {partner && <p>Chatting with: {partner}</p>}
      <button onClick={onLogout}>Logout</button>
      <button onClick={endSession} disabled={!sessionId}>End Session</button>
      <div className="messages">
        {messages.map((msg, index) => (
          <div key={index}>{msg.user}: {msg.content}</div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={sendMessage}>
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          placeholder="Type a message..."
          disabled={!sessionId}
        />
        <button type="submit" disabled={!sessionId}>Send</button>
      </form>
    </div>
  );
}

export default Chat;