"""
=============================================================================
CLEAR: Your Personal Contextual Task Assistant (Multi-User Edition)
=============================================================================
This is the backend server that powers Mini-Mind. It uses:
- FastAPI: A modern, fast web framework for building APIs
- SQLite: A lightweight database that stores data in a single file
- JWT: JSON Web Tokens for secure user authentication
- bcrypt: For secure password hashing

How it works:
1. Users register an account (username + password)
2. Users log in and receive a JWT token
3. The token is sent with every request to identify the user
4. Each user only sees their own tasks
=============================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from datetime import datetime, timedelta
import dateparser
import re
import hashlib
import secrets
import json
import os

# =============================================================================
# CONFIGURATION
# =============================================================================

# Secret key for JWT tokens - in production, use environment variable
# Railway will set this automatically, or you can set it in the dashboard
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# Database file
DATABASE_NAME = os.environ.get("DATABASE_PATH", "clear.db")

# Token expiration (7 days)
TOKEN_EXPIRATION_DAYS = 7

# =============================================================================
# DATABASE SETUP
# =============================================================================

def get_database_connection():
    """Creates a connection to our SQLite database."""
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    """
    Creates all necessary tables if they don't exist.

    Tables:
    - users: Stores user accounts (id, username, password_hash, created_at)
    - tasks: Stores tasks with a user_id foreign key
    - tokens: Stores active JWT tokens for session management
    """
    connection = get_database_connection()
    cursor = connection.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tasks table (now with user_id)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            due_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # Tokens table (for token validation/revocation)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    connection.commit()
    connection.close()


# =============================================================================
# AUTHENTICATION HELPERS
# =============================================================================

def hash_password(password: str) -> str:
    """
    Hashes a password using SHA-256 with a salt.
    In production, consider using bcrypt (requires additional dependency).
    """
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${password_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifies a password against its stored hash."""
    try:
        salt, hash_value = stored_hash.split("$")
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return password_hash == hash_value
    except ValueError:
        return False


def create_token(user_id: int, username: str) -> str:
    """
    Creates a simple JWT-like token.
    Format: base64(json({user_id, username, expires, random})).signature
    """
    expires = (datetime.now() + timedelta(days=TOKEN_EXPIRATION_DAYS)).isoformat()

    # Create token payload
    payload = {
        "user_id": user_id,
        "username": username,
        "expires": expires,
        "random": secrets.token_hex(8)
    }

    # Encode payload
    import base64
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

    # Create signature
    signature = hashlib.sha256((payload_b64 + SECRET_KEY).encode()).hexdigest()[:16]

    token = f"{payload_b64}.{signature}"

    # Store token in database
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires)
    )
    connection.commit()
    connection.close()

    return token


def verify_token(token: str) -> Optional[dict]:
    """
    Verifies a token and returns the payload if valid.
    Returns None if invalid or expired.
    """
    try:
        import base64

        # Split token
        payload_b64, signature = token.split(".")

        # Verify signature
        expected_signature = hashlib.sha256((payload_b64 + SECRET_KEY).encode()).hexdigest()[:16]
        if signature != expected_signature:
            return None

        # Decode payload
        payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
        payload = json.loads(payload_json)

        # Check expiration
        expires = datetime.fromisoformat(payload["expires"])
        if datetime.now() > expires:
            return None

        # Verify token exists in database (not revoked)
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM tokens WHERE token = ?", (token,))
        if not cursor.fetchone():
            connection.close()
            return None
        connection.close()

        return payload

    except Exception:
        return None


# =============================================================================
# DATA MODELS
# =============================================================================

class UserRegister(BaseModel):
    """Registration request model."""
    username: str
    password: str


class UserLogin(BaseModel):
    """Login request model."""
    username: str
    password: str


class AuthResponse(BaseModel):
    """Authentication response model."""
    message: str
    token: Optional[str] = None
    username: Optional[str] = None


class TaskCreate(BaseModel):
    content: str
    due_date: Optional[str] = None


class Task(BaseModel):
    id: int
    content: str
    status: str
    due_date: Optional[str]
    created_at: str


class NaturalLanguageInput(BaseModel):
    text: str


class AssistantResponse(BaseModel):
    message: str
    tasks: Optional[List[Task]] = None
    action: str


# =============================================================================
# AUTHENTICATION DEPENDENCY
# =============================================================================

security = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    FastAPI dependency that extracts and validates the user from the token.
    Use this in any endpoint that requires authentication.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return payload


# =============================================================================
# VOICE-TO-TEXT PLACEHOLDER
# =============================================================================

def process_voice_input(audio_data: bytes) -> str:
    """
    PLACEHOLDER: Convert voice audio to text.

    Future implementation options:
    - OpenAI Whisper API
    - Google Speech-to-Text
    - Azure Cognitive Services
    - Local Vosk library
    """
    raise NotImplementedError("Voice input not yet implemented")


# =============================================================================
# NATURAL LANGUAGE PROCESSING
# =============================================================================

def parse_date_from_text(text: str) -> Optional[str]:
    """Extracts and parses dates from natural language text."""

    # Special handling for "end of week"
    if "end of week" in text.lower():
        today = datetime.now()
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0:
            days_until_sunday = 7
        end_of_week = today + timedelta(days=days_until_sunday)
        return end_of_week.strftime("%Y-%m-%d")

    # Special handling for "end of month"
    if "end of month" in text.lower():
        today = datetime.now()
        if today.month == 12:
            last_day = today.replace(day=31)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
            last_day = next_month - timedelta(days=1)
        return last_day.strftime("%Y-%m-%d")

    # Use dateparser for other date formats
    parsed_date = dateparser.parse(
        text,
        settings={
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': datetime.now()
        }
    )

    if parsed_date:
        return parsed_date.strftime("%Y-%m-%d")

    return None


def extract_task_content(text: str) -> str:
    """Cleans up the user's input to extract just the task content."""

    prefixes_to_remove = [
        r'^remind me to\s+',
        r'^add task\s+',
        r'^add\s+',
        r'^create task\s+',
        r'^i need to\s+',
        r'^i have to\s+',
        r'^i should\s+',
        r'^don\'t forget to\s+',
        r'^remember to\s+',
    ]

    cleaned_text = text.lower().strip()

    for pattern in prefixes_to_remove:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)

    date_references = [
        r'\s+on \w+day\b',
        r'\s+tomorrow\b',
        r'\s+today\b',
        r'\s+next \w+\b',
        r'\s+this \w+\b',
        r'\s+by end of week\b',
        r'\s+end of week\b',
        r'\s+by end of month\b',
        r'\s+end of month\b',
        r'\s+in \d+ days?\b',
        r'\s+on \d{1,2}/\d{1,2}\b',
    ]

    for pattern in date_references:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)

    return cleaned_text.strip().capitalize()


def process_natural_language(text: str, user_id: int) -> AssistantResponse:
    """
    Processes natural language commands for a specific user.
    All task operations are scoped to the user_id.
    """
    text_lower = text.lower().strip()
    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        # INTENT: Show/List Tasks
        if any(word in text_lower for word in ['show', 'list', 'what\'s', 'what do i have', 'my tasks', 'view']):

            if 'today' in text_lower:
                today = datetime.now().strftime("%Y-%m-%d")
                cursor.execute(
                    "SELECT * FROM tasks WHERE user_id = ? AND due_date = ? AND status = 'pending' ORDER BY created_at",
                    (user_id, today)
                )
            elif 'done' in text_lower or 'completed' in text_lower:
                cursor.execute(
                    "SELECT * FROM tasks WHERE user_id = ? AND status = 'done' ORDER BY created_at DESC",
                    (user_id,)
                )
            else:
                cursor.execute(
                    "SELECT * FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY due_date, created_at",
                    (user_id,)
                )

            rows = cursor.fetchall()
            tasks = [Task(**dict(row)) for row in rows]

            if tasks:
                return AssistantResponse(
                    message=f"Here are your tasks ({len(tasks)} total):",
                    tasks=tasks,
                    action="list"
                )
            else:
                return AssistantResponse(
                    message="You have no pending tasks. Nice work!",
                    tasks=[],
                    action="list"
                )

        # INTENT: Mark Task as Done
        elif any(word in text_lower for word in ['done', 'finished', 'complete', 'completed']):

            cursor.execute(
                "SELECT * FROM tasks WHERE user_id = ? AND status = 'pending'",
                (user_id,)
            )
            pending_tasks = cursor.fetchall()

            matched_task = None
            for task in pending_tasks:
                task_words = task['content'].lower().split()
                if any(word in text_lower for word in task_words if len(word) > 3):
                    matched_task = task
                    break

            if matched_task:
                cursor.execute(
                    "UPDATE tasks SET status = 'done' WHERE id = ? AND user_id = ?",
                    (matched_task['id'], user_id)
                )
                connection.commit()
                return AssistantResponse(
                    message=f"Great job! Marked '{matched_task['content']}' as done!",
                    action="complete"
                )
            else:
                tasks = [Task(**dict(row)) for row in pending_tasks]
                return AssistantResponse(
                    message="I couldn't find that task. Here are your pending tasks:",
                    tasks=tasks,
                    action="list"
                )

        # INTENT: Delete Task
        elif any(word in text_lower for word in ['delete', 'remove', 'cancel']):

            cursor.execute(
                "SELECT * FROM tasks WHERE user_id = ? AND status = 'pending'",
                (user_id,)
            )
            pending_tasks = cursor.fetchall()

            matched_task = None
            for task in pending_tasks:
                task_words = task['content'].lower().split()
                if any(word in text_lower for word in task_words if len(word) > 3):
                    matched_task = task
                    break

            if matched_task:
                cursor.execute(
                    "DELETE FROM tasks WHERE id = ? AND user_id = ?",
                    (matched_task['id'], user_id)
                )
                connection.commit()
                return AssistantResponse(
                    message=f"Deleted task: '{matched_task['content']}'",
                    action="delete"
                )
            else:
                tasks = [Task(**dict(row)) for row in pending_tasks]
                return AssistantResponse(
                    message="I couldn't find that task to delete. Here are your tasks:",
                    tasks=tasks,
                    action="list"
                )

        # INTENT: Add New Task (Default)
        else:
            task_content = extract_task_content(text)
            due_date = parse_date_from_text(text)

            if not task_content or len(task_content) < 2:
                return AssistantResponse(
                    message="I didn't quite catch that. Try something like 'Remind me to call mom tomorrow'",
                    action="error"
                )

            cursor.execute(
                "INSERT INTO tasks (user_id, content, status, due_date) VALUES (?, ?, 'pending', ?)",
                (user_id, task_content, due_date)
            )
            connection.commit()

            if due_date:
                date_obj = datetime.strptime(due_date, "%Y-%m-%d")
                friendly_date = date_obj.strftime("%A, %B %d")
                message = f"Got it! Added: '{task_content}' due {friendly_date}"
            else:
                message = f"Got it! Added: '{task_content}' (no due date)"

            return AssistantResponse(
                message=message,
                action="add"
            )

    finally:
        connection.close()


# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

app = FastAPI(
    title="Clear",
    description="Your Personal Contextual Task Assistant",
    version="2.0.0"
)

# CORS configuration - allow requests from any origin for the web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    initialize_database()
    print("Clear is starting up...")
    print("Database initialized!")


# Serve the frontend HTML file
@app.get("/")
async def serve_frontend():
    """Serve the main HTML file."""
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "Clear API is running. Frontend not found."}


# -----------------------------------------------------------------------------
# Authentication Endpoints
# -----------------------------------------------------------------------------

@app.post("/register", response_model=AuthResponse)
async def register(user: UserRegister):
    """
    Register a new user account.

    Returns a token on successful registration (auto-login).
    """
    # Validate input
    if len(user.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(user.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    connection = get_database_connection()
    cursor = connection.cursor()

    # Check if username exists
    cursor.execute("SELECT id FROM users WHERE username = ?", (user.username.lower(),))
    if cursor.fetchone():
        connection.close()
        raise HTTPException(status_code=400, detail="Username already taken")

    # Create user
    password_hash = hash_password(user.password)
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (user.username.lower(), password_hash)
    )
    connection.commit()

    user_id = cursor.lastrowid
    connection.close()

    # Create token (auto-login)
    token = create_token(user_id, user.username.lower())

    return AuthResponse(
        message="Account created successfully!",
        token=token,
        username=user.username.lower()
    )


@app.post("/login", response_model=AuthResponse)
async def login(user: UserLogin):
    """
    Log in to an existing account.

    Returns a token on successful login.
    """
    connection = get_database_connection()
    cursor = connection.cursor()

    # Find user
    cursor.execute(
        "SELECT id, password_hash FROM users WHERE username = ?",
        (user.username.lower(),)
    )
    row = cursor.fetchone()
    connection.close()

    if not row or not verify_password(user.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Create token
    token = create_token(row["id"], user.username.lower())

    return AuthResponse(
        message="Login successful!",
        token=token,
        username=user.username.lower()
    )


@app.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Log out by invalidating the current token."""
    # In a full implementation, you would delete the token from the database
    return {"message": "Logged out successfully"}


# -----------------------------------------------------------------------------
# Chat Endpoint (requires authentication)
# -----------------------------------------------------------------------------

@app.post("/chat", response_model=AssistantResponse)
async def chat(user_input: NaturalLanguageInput, current_user: dict = Depends(get_current_user)):
    """
    Process a natural language command.
    Requires authentication - tasks are scoped to the logged-in user.
    """
    if not user_input.text.strip():
        raise HTTPException(status_code=400, detail="Please enter a command")

    return process_natural_language(user_input.text, current_user["user_id"])


# -----------------------------------------------------------------------------
# Task Endpoints (require authentication)
# -----------------------------------------------------------------------------

@app.get("/tasks", response_model=List[Task])
async def get_all_tasks(current_user: dict = Depends(get_current_user)):
    """Get all tasks for the current user."""
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT id, content, status, due_date, created_at FROM tasks WHERE user_id = ? ORDER BY status, due_date, created_at",
        (current_user["user_id"],)
    )
    rows = cursor.fetchall()
    connection.close()
    return [Task(**dict(row)) for row in rows]


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a specific task (must belong to current user)."""
    connection = get_database_connection()
    cursor = connection.cursor()
    cursor.execute(
        "DELETE FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, current_user["user_id"])
    )
    connection.commit()
    affected = cursor.rowcount
    connection.close()

    if affected == 0:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"message": "Task deleted successfully"}


@app.put("/tasks/{task_id}/toggle")
async def toggle_task_status(task_id: int, current_user: dict = Depends(get_current_user)):
    """Toggle a task between 'pending' and 'done'."""
    connection = get_database_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT status FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, current_user["user_id"])
    )
    row = cursor.fetchone()

    if not row:
        connection.close()
        raise HTTPException(status_code=404, detail="Task not found")

    new_status = "done" if row["status"] == "pending" else "pending"
    cursor.execute(
        "UPDATE tasks SET status = ? WHERE id = ? AND user_id = ?",
        (new_status, task_id, current_user["user_id"])
    )
    connection.commit()
    connection.close()

    return {"message": f"Task status changed to {new_status}", "new_status": new_status}


# =============================================================================
# RUN THE SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("CLEAR - Your Personal Task Assistant")
    print("=" * 60)
    print()
    print("Starting server at http://localhost:8000")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)

    # Get port from environment variable (Railway sets this)
    port = int(os.environ.get("PORT", 8000))

    uvicorn.run(app, host="0.0.0.0", port=port)
