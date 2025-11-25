# -*- coding: utf-8 -*-
"""
Checkpoint Manager - Handles resumable session state
"""

import json
import pickle
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple, Set
import uuid
from config import CHECKPOINT_DIR


class CheckpointManager:
    """Manages query checkpoints for resumable sessions"""

    def __init__(self, checkpoint_dir: str = CHECKPOINT_DIR):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)

    def _convert_to_serializable(self, obj: Any) -> Any:
        """Convert sets and other non-serializable types to serializable formats"""
        if isinstance(obj, set):
            return {'__set__': list(obj)}
        elif isinstance(obj, dict):
            return {k: self._convert_to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._convert_to_serializable(item) for item in obj]
        else:
            return obj

    def _convert_from_serializable(self, obj: Any) -> Any:
        """
        Recursively convert serialized data back to original types.
        Handles: dicts, lists, tuples, sets (marked as {'__set__': [...]})
        """
        if obj is None:
            return obj
        
        if isinstance(obj, dict):
            # Check for set marker (must be only key)
            if len(obj) == 1 and '__set__' in obj:
                items = obj['__set__']
                if isinstance(items, list):
                    return set(items)
                return set([items])
            
            # Otherwise recurse into dict
            return {
                k: self._convert_from_serializable(v) 
                for k, v in obj.items()
            }
        
        elif isinstance(obj, list):
            # Recurse into list items
            return [
                self._convert_from_serializable(item)
                for item in obj
            ]
        
        elif isinstance(obj, tuple):
            # Recurse into tuple items, maintain tuple type
            return tuple(
                self._convert_from_serializable(item)
                for item in obj
            )
        
        else:
            # Primitive type, return as-is
            return obj

    def create_checkpoint(self, session_id: str, state: Dict[str, Any]) -> str:
        """Create and save checkpoint with proper data type handling"""
        checkpoint_id = str(uuid.uuid4())
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"

        # Convert state to serializable format
        serializable_state = self._convert_to_serializable(state)

        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'state': serializable_state
        }

        with open(checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)

        print(f"[SAVE] Checkpoint saved: {checkpoint_id}")
        return checkpoint_id

    def load_checkpoint(self, session_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Load checkpoint by ID and restore data types"""
        checkpoint_file = self.checkpoint_dir / f"{session_id}_{checkpoint_id}.pkl"

        if not checkpoint_file.exists():
            print(f"[ERR] Checkpoint file not found: {checkpoint_file}")
            return None

        try:
            with open(checkpoint_file, 'rb') as f:
                checkpoint_data = pickle.load(f)

            # Convert state back from serializable format
            checkpoint_data['state'] = self._convert_from_serializable(checkpoint_data['state'])
            
            return checkpoint_data
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

                # Extract checkpoint_id from filename (source of truth)
                # Filename format: {session_id}_{checkpoint_id}.pkl
                checkpoint_id = checkpoint_file.stem.split('_', 1)[1] if '_' in checkpoint_file.stem else None
                
                if not checkpoint_id:
                    print(f"[WARN] Could not extract checkpoint_id from filename: {checkpoint_file.name}")
                    continue

                checkpoints.append({
                    'checkpoint_id': checkpoint_id,
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

                # Convert state back from serializable format
                if 'state' in data:
                    data['state'] = self._convert_from_serializable(data['state'])

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
        else:
            # Debug: list available checkpoints for this session
            pattern = f"{session_id}_*.pkl"
            available_files = list(self.checkpoint_dir.glob(pattern))
            print(f"[DEL] Checkpoint file not found: {checkpoint_file}")
            print(f"[DEL] Available checkpoints for session {session_id}:")
            for f in available_files:
                extracted_id = f.stem.split('_', 1)[1] if '_' in f.stem else 'N/A'
                print(f"  - {f.name} (extracted checkpoint_id: {extracted_id})")

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