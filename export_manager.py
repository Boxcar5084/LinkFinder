import csv
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime
from config import EXPORT_DIR

class ExportManager:
    """Handles CSV and JSON exports"""
    
    def __init__(self, export_dir: str = EXPORT_DIR):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(exist_ok=True)
    
    def export_to_csv(self, results: Dict[str, Any], session_id: str) -> str:
        """Export to CSV format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = self.export_dir / f"connections_{session_id}_{timestamp}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Source', 'Target', 'Meeting Points', 'Path Count'])
            
            for conn in results.get('connections_found', []):
                writer.writerow([
                    conn['source'],
                    conn['target'],
                    '|'.join(conn['meeting_points']),
                    conn['path_count']
                ])
        
        print(f"✅ CSV saved: {csv_file}")
        return str(csv_file)
    
    def export_to_json(self, results: Dict[str, Any], session_id: str) -> str:
        """Export to JSON format"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.export_dir / f"connections_{session_id}_{timestamp}.json"
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        print(f"✅ JSON saved: {json_file}")
        return str(json_file)
    
    def export_both(self, results: Dict[str, Any], session_id: str) -> Tuple[str, str]:
        """Export to both formats"""
        csv_path = self.export_to_csv(results, session_id)
        json_path = self.export_to_json(results, session_id)
        return csv_path, json_path
