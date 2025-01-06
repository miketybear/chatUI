# app.py
import streamlit as st
import requests
import uuid
import sqlite3
import json
from datetime import datetime
import pyperclip
import os
from dotenv import load_dotenv
import contextlib
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants from .env
API_URL = os.getenv('N8N_WEBHOOK_URL')
BEARER_TOKEN = os.getenv('BEARER_TOKEN')
DB_PATH = os.getenv('DB_PATH')

# Validate required env vars
if not all([API_URL, BEARER_TOKEN, DB_PATH]):
    raise ValueError("Missing required environment variables. Check .env file.")

@contextlib.contextmanager
def get_db_connection():
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Create sessions table
            c.execute('''CREATE TABLE IF NOT EXISTS sessions
                        (session_id TEXT PRIMARY KEY, created_at TIMESTAMP)''')
            # Create messages table
            c.execute('''CREATE TABLE IF NOT EXISTS messages
                        (id INTEGER PRIMARY KEY, session_id TEXT, 
                         user_message TEXT, llm_response TEXT, timestamp TIMESTAMP,
                         FOREIGN KEY (session_id) REFERENCES sessions(session_id))''')
            conn.commit()
            logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

def save_message(session_id, user_message, llm_response):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO messages (session_id, user_message, llm_response, timestamp) VALUES (?, ?, ?, ?)", (session_id, user_message, llm_response, datetime.now()))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to save message: {e}")
        raise

def get_sessions():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            return c.execute("SELECT session_id, created_at FROM sessions ORDER BY created_at DESC").fetchall()
    except sqlite3.Error as e:
        logger.error(f"Failed to get sessions: {e}")
        raise

def get_session_messages(session_id):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            messages = c.execute("SELECT user_message, llm_response FROM messages WHERE session_id = ? ORDER BY timestamp", (session_id,)).fetchall()
            return messages
    except sqlite3.Error as e:
        logger.error(f"Failed to get session messages: {e}")
        raise

def create_session(session_id):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO sessions (session_id, created_at) VALUES (?, ?)", (session_id, datetime.now()))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Failed to create session: {e}")
        raise

# Initialize database before any operations
init_db()

# Initialize session state
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    create_session(st.session_state.session_id)

# Streamlit UI
st.title("Chat with LLM")

# Sidebar with session history
with st.sidebar:
    st.header("Chat History")
    sessions = get_sessions()
    for session_id, created_at in sessions:
        if st.button(f"Session {session_id[:8]} - {created_at}"):
            st.session_state.session_id = session_id
            st.experimental_rerun()

# Chat interface
def send_message(message):
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "sessionId": st.session_state.session_id,
        "chatInput": message
    }
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()["output"]

# Display chat history
messages = get_session_messages(st.session_state.session_id)
for user_msg, llm_resp in messages:
    with st.chat_message("user"):
        st.write(user_msg)
    with st.chat_message("assistant"):
        st.write(llm_resp)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Retry", key=f"retry_{hash(user_msg)}"):
                new_response = send_message(user_msg)
                save_message(st.session_state.session_id, user_msg, new_response)
                st.experimental_rerun()
        with col2:
            if st.button("📋 Copy", key=f"copy_{hash(user_msg)}"):
                pyperclip.copy(llm_resp)
                st.toast("Response copied to clipboard!")

# Chat input
if prompt := st.chat_input("Type your message here..."):
    with st.chat_message("user"):
        st.write(prompt)
    
    with st.chat_message("assistant"):
        response = send_message(prompt)
        st.write(response)
        save_message(st.session_state.session_id, prompt, response)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Retry", key=f"retry_{hash(prompt)}"):
                new_response = send_message(prompt)
                save_message(st.session_state.session_id, prompt, new_response)
                st.experimental_rerun()
        with col2:
            if st.button("📋 Copy", key=f"copy_{hash(prompt)}"):
                pyperclip.copy(response)
                st.toast("Response copied to clipboard!")