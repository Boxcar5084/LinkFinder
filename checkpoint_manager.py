# -*- coding: utf-8 -*-

import json
import pickle
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import uuid
from config import CHECKPOINT_DIR

class CheckpointManager:
    """Manages query checkpoints for resumable sessions"""

    def __init__(self, checkpoint_dir: str = CHECKPOINT_DIR):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)

    def create_checkpoint(self, session_id: str, state: Dict[str, Any]) -> str:
        """Create and save checkpoint"""
        checkpoint_id = str(uuid.uuid4())
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"

        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'state': state
        }

        with open(checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)

        print(f"[SAVE] Checkpoint saved: {checkpoint_id}")
        return checkpoint_id

    def load_checkpoint(self, session_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Load checkpoint by ID"""
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"

        if not checkpoint_file.exists():
            print(f"[ERR] Checkpoint file not found: {checkpoint_file}")
            return None

        try:
            with open(checkpoint_file, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"[ERR] Failed to load checkpoint: {e}")
            return None

    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """List all checkpoints for a session"""
        checkpoints = []
        pattern = f"{session_id}_*.pkl"

        for checkpoint_file in self.checkpoint_dir.glob(pattern):
            try:
                with open(checkpoint_file, 'rb') as f:
                    data = pickle.load(f)
                    checkpoints.append({
                        'checkpoint_id': data['state'].get('checkpoint_id',
                                                           checkpoint_file.stem.split('_', 1)[1]),
                        'timestamp': data['timestamp'],
                        'session_id': data['session_id']
                    })
            except Exception as e:
                print(f"[WARN] Failed to load checkpoint {checkpoint_file}: {e}")
                continue

        # Sort by timestamp, most recent first
        checkpoints.sort(key=lambda x: x['timestamp'], reverse=True)
        return checkpoints

    def get_most_recent_checkpoint(self) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """
        Get the most recent checkpoint across all sessions.
        Returns:
            Tuple of (session_id, checkpoint_id, checkpoint_data) or None if no checkpoints exist
        """
        all_checkpoints = []

        # Iterate through all checkpoint files
        for checkpoint_file in self.checkpoint_dir.glob("*.pkl"):
            try:
                with open(checkpoint_file, 'rb') as f:
                    data = pickle.load(f)
                    session_id = data.get('session_id')
                    timestamp = datetime.fromisoformat(data.get('timestamp', ''))
                    checkpoint_id = checkpoint_file.stem.split('_', 1)[1]  # Extract from filename

                    all_checkpoints.append({
                        'session_id': session_id,
                        'checkpoint_id': checkpoint_id,
                        'timestamp': timestamp,
                        'data': data
                    })
            except Exception as e:
                print(f"[WARN] Failed to load checkpoint {checkpoint_file}: {e}")
                continue

        if not all_checkpoints:
            return None

        # Sort by timestamp, most recent first
        all_checkpoints.sort(key=lambda x: x['timestamp'], reverse=True)
        most_recent = all_checkpoints[0]

        return (
            most_recent['session_id'],
            most_recent['checkpoint_id'],
            most_recent['data']
        )

    def get_latest_checkpoint_for_session(self, session_id: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Get the most recent checkpoint for a specific session.
        Returns:
            Tuple of (checkpoint_id, checkpoint_data) or None if no checkpoints exist
        """
        checkpoints = self.list_checkpoints(session_id)

        if not checkpoints:
            return None

        # list_checkpoints already sorts by most recent first
        most_recent = checkpoints[0]
        checkpoint = self.load_checkpoint(session_id, most_recent['checkpoint_id'])

        if checkpoint:
            return (most_recent['checkpoint_id'], checkpoint)

        return None

    def delete_checkpoint(self, session_id: str, checkpoint_id: str) -> bool:
        """Delete a specific checkpoint file"""
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"

        if checkpoint_file.exists():
            try:
                checkpoint_file.unlink()
                print(f"[DEL] Checkpoint deleted: {checkpoint_id}")
                return True
            except Exception as e:
                print(f"[ERR] Failed to delete checkpoint: {e}")
                return False

        return False

    def cleanup_session_checkpoints(self, session_id: str) -> int:
        """Delete all checkpoints for a session. Returns count deleted."""
        pattern = f"{session_id}_*.pkl"
        deleted_count = 0

        for checkpoint_file in self.checkpoint_dir.glob(pattern):
            try:
                checkpoint_file.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"[ERR] Failed to delete {checkpoint_file}: {e}")

        if deleted_count > 0:
            print(f"[DEL] Cleaned up {deleted_count} checkpoints for session {session_id}")

        return deleted_count