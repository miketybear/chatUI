import os
from dotenv import load_dotenv
import streamlit as st
import requests
import uuid
import json
import sqlite3
from datetime import datetime

# Database setup
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Create tables if they don't exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            created_at TIMESTAMP,
            last_updated TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions (session_id)
        )
    ''')
    conn.commit()
    conn.close()

def save_message(session_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_time = datetime.now()
    
    # Insert message
    c.execute('''
        INSERT INTO messages (session_id, role, content, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (session_id, role, content, current_time))
    
    # Update session last_updated
    c.execute('''
        UPDATE chat_sessions SET last_updated = ?
        WHERE session_id = ?
    ''', (current_time, session_id))
    
    conn.commit()
    conn.close()

def create_new_session():
    session_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_time = datetime.now()
    c.execute('''
        INSERT INTO chat_sessions (session_id, created_at, last_updated)
        VALUES (?, ?, ?)
    ''', (session_id, current_time, current_time))
    conn.commit()
    conn.close()
    return session_id

def get_session_messages(session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT role, content FROM messages 
        WHERE session_id = ?
        ORDER BY timestamp
    ''', (session_id,))
    messages = [{"role": role, "content": content} for role, content in c.fetchall()]
    conn.close()
    return messages

def get_first_user_message(session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT content FROM messages 
        WHERE session_id = ? AND role = 'user'
        ORDER BY timestamp
        LIMIT 1
    ''', (session_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else ""

def get_all_sessions():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Only get sessions that have messages
    c.execute('''
        SELECT DISTINCT chat_sessions.session_id, chat_sessions.created_at, chat_sessions.last_updated 
        FROM chat_sessions 
        INNER JOIN messages ON chat_sessions.session_id = messages.session_id
        ORDER BY chat_sessions.last_updated DESC
    ''')
    sessions = c.fetchall()
    conn.close()
    return sessions

# Load environment variables
load_dotenv()

# Configuration
WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
DB_PATH = os.getenv("DB_PATH")

def send_message(message):
    """
    Send message to n8n webhook and return the response
    """
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "sessionId": st.session_state.session_id,
        "chatInput": message
    }
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()["output"]
    except requests.exceptions.RequestException as e:
        st.error(f"Error communicating with the server: {str(e)}")
        return None

# Initialize database
init_db()

# Initialize session state
if 'session_id' not in st.session_state:
    st.session_state.session_id = create_new_session()
if 'messages' not in st.session_state:
    st.session_state.messages = []

# Sidebar for chat history
with st.sidebar:
    st.title("Chat History")
    
    # Start New Chat button
    if st.button("Start New Chat"):
        st.session_state.session_id = create_new_session()
        st.session_state.messages = []
        st.rerun()
    
    # Display chat sessions
    sessions = get_all_sessions()
    for session_id, created_at, last_updated in sessions:
        first_message = get_first_user_message(session_id)
        # Truncate message to 50 characters and add ellipsis if needed
        display_text = (first_message[:24] + "...") if len(first_message) > 27 else first_message
        
        if st.button(display_text, key=session_id):
            st.session_state.session_id = session_id
            st.session_state.messages = get_session_messages(session_id)
            st.rerun()

# Main chat interface
st.title("Chat Interface")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Chat input
if prompt := st.chat_input("Enter your message"):
    # Display user message
    with st.chat_message("user"):
        st.write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_message(st.session_state.session_id, "user", prompt)
    
    # Get and display assistant response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = send_message(prompt)
            if response:
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                save_message(st.session_state.session_id, "assistant", response)