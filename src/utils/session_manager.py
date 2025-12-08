import os
import shutil
import datetime
import streamlit as st

class SessionManager:
    def __init__(self, base_dir="workspace", db_path="state.db"):
        self.base_dir = os.path.abspath(base_dir)
        self.db_path = os.path.abspath(db_path)
        
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)
            
        self._init_metadata_db()
        
    def _init_metadata_db(self):
        """Creates the metadata table if it doesn't exist."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_metadata (
                session_id TEXT PRIMARY KEY,
                model_name TEXT,
                created_at TIMESTAMP,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cached_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                total_cost REAL DEFAULT 0.0
            )
        """)
        conn.commit()
        conn.close()

    def get_all_sessions(self):
        """Returns a sorted list of session directories (newest first)."""
        if not os.path.exists(self.base_dir):
            return []
        sessions = [d for d in os.listdir(self.base_dir) if os.path.isdir(os.path.join(self.base_dir, d))]
        return sorted(sessions, reverse=True)

    def create_session(self, tag, model_name="gemini-2.5-flash"):
        """Creates a new session directory using the tag. Raises FileExistsError if it exists."""
        if not tag:
            raise ValueError("Tag is required.")
            
        # Sanitize tag
        safe_tag = "".join(c for c in tag if c.isalnum() or c in ('-', '_'))
        if not safe_tag:
             raise ValueError("Invalid tag format.")
             
        session_name = safe_tag
        path = os.path.join(self.base_dir, session_name)
        
        if os.path.exists(path):
            raise FileExistsError(f"Session '{session_name}' already exists.")
            
        os.makedirs(path)
        
        # Store Metadata
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO session_metadata (session_id, model_name, created_at) VALUES (?, ?, ?)", 
                       (session_name, model_name, datetime.datetime.now()))
        conn.commit()
        conn.close()
        
        return session_name

    def get_session_metadata(self, session_id):
        """Retrieves metadata for a session. Returns dict or None."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM session_metadata WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # Columns: session_id, model_name, created_at, input, output, cached, total, cost
            return {
                "session_id": row[0],
                "model_name": row[1],
                "created_at": row[2],
                "input_tokens": row[3],
                "output_tokens": row[4],
                "cached_tokens": row[5],
                "total_tokens": row[6],
                "total_cost": row[7]
            }
        return None

    def update_session_stats(self, session_id, input_t, output_t, cached_t, cost):
        """Updates (increments) the stats for a session."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # We update by ADDING the new delta (assumes caller sends delta)
        # OR we can update absolute values if caller tracks total.
        # Let's assume absolute totals for better consistency with app state.
        cursor.execute("""
            UPDATE session_metadata 
            SET input_tokens = ?, output_tokens = ?, cached_tokens = ?, total_tokens = ?, total_cost = ?
            WHERE session_id = ?
        """, (input_t, output_t, cached_t, input_t + output_t + cached_t, cost, session_id))
        conn.commit()
        conn.close()

    def clear_all_sessions(self):
        """Deletes all workspace folders and the database."""
        # Clear Workspace
        if os.path.exists(self.base_dir):
            for item in os.listdir(self.base_dir):
                item_path = os.path.join(self.base_dir, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
        
        # Clear DB
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                st.error("Could not delete database file. It might be in use.")
                
    def get_workspace_path(self, session_id):
        return os.path.join(self.base_dir, session_id)
