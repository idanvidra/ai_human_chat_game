# main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
import motor.motor_asyncio
import random
import json

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React app's address
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection
client = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
db = client.chatapp

# Models
class User(BaseModel):
    username: str
    hashed_password: str
    
class ChatUser:
    def __init__(self, username: str, websocket: WebSocket):
        self.username = username
        self.websocket = websocket
    
class PairingManager:
    def __init__(self):
        self.waiting_users: List[ChatUser] = []
        self.active_pairs: Dict[str, List[ChatUser]] = {}

    async def add_user(self, user: ChatUser):
        if self.waiting_users:
            partner = self.waiting_users.pop(0)
            session_id = f"{user.username}-{partner.username}"
            self.active_pairs[session_id] = [user, partner]
            await self.start_session(session_id)
        else:
            self.waiting_users.append(user)

    async def start_session(self, session_id: str):
        users = self.active_pairs[session_id]
        for user in users:
            await user.websocket.send_json({
                "type": "session_start",
                "session_id": session_id,
                "partner": users[1].username if user == users[0] else users[0].username
            })

    async def end_session(self, session_id: str):
        if session_id in self.active_pairs:
            users = self.active_pairs.pop(session_id)
            for user in users:
                await user.websocket.send_json({
                    "type": "session_end",
                    "session_id": session_id
                })

pairing_manager = PairingManager()

class ChatSession(BaseModel):
    session_id: str
    user1: str
    user2: str
    is_ai: bool
    messages: List[dict]
    created_at: datetime

class Rating(BaseModel):
    session_id: str
    user: str
    rating: int
    is_human_guess: bool

# Authentication
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = await db.users.find_one({"username": username})
    if user is None:
        raise credentials_exception
    return User(**user)

# Routes
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db.users.find_one({"username": form_data.username})
    if not user or user["hashed_password"] != form_data.password:  # In production, use proper password hashing
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/register")
async def register(user: User):
    existing_user = await db.users.find_one({"username": user.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    await db.users.insert_one(user.dict())
    return {"message": "User registered successfully"}

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

# WebSocket endpoint for chat
@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            await websocket.close(code=1008)  # Policy Violation
            return
    except JWTError:
        await websocket.close(code=1008)  # Policy Violation
        return

    await websocket.accept()
    chat_user = ChatUser(username=username, websocket=websocket)
    await pairing_manager.add_user(chat_user)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message["type"] == "chat_message":
                session_id = message["session_id"]
                if session_id in pairing_manager.active_pairs:
                    users = pairing_manager.active_pairs[session_id]
                    for u in users:
                        await u.websocket.send_json({
                            "type": "chat_message",
                            "session_id": session_id,
                            "user": username,
                            "message": message["content"]
                        })
            elif message["type"] == "end_session":
                await pairing_manager.end_session(message["session_id"])
    except WebSocketDisconnect:
        # Handle disconnection
        for session_id, users in pairing_manager.active_pairs.items():
            if chat_user in users:
                await pairing_manager.end_session(session_id)
                break
        if chat_user in pairing_manager.waiting_users:
            pairing_manager.waiting_users.remove(chat_user)

# API routes for chat sessions and ratings
@app.post("/chat-sessions")
async def create_chat_session(session: ChatSession, current_user: User = Depends(get_current_user)):
    result = await db.chat_sessions.insert_one(session.dict())
    return {"message": "Chat session created", "session_id": str(result.inserted_id)}

@app.get("/chat-sessions/{session_id}")
async def get_chat_session(session_id: str, current_user: User = Depends(get_current_user)):
    session = await db.chat_sessions.find_one({"session_id": session_id})
    if session:
        return session
    raise HTTPException(status_code=404, detail="Chat session not found")

@app.post("/ratings")
async def submit_rating(rating: Rating, current_user: User = Depends(get_current_user)):
    result = await db.ratings.insert_one(rating.dict())
    return {"message": "Rating submitted", "rating_id": str(result.inserted_id)}

# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
# TO RUN MONGODB AS A SERVICE # brew services start mongodb-community@7.0
# TO RUN THE FASTAPI APP # uvicorn main:app --reload
# TO ACCESS THE API DOCUMENTATION # http://127.0.0.1:8000/docs
# Open another termainal and run: first move (cd) to the chat-frontend path and then run npm start 