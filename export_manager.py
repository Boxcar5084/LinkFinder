# -*- coding: utf-8 -*-

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
        self._active_exports = {}  # session_id -> {csv_path, json_path, csv_writer, json_data}

    def export_to_csv(self, results: Dict[str, Any], session_id: str) -> str:
        """Export to CSV format - connections only"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = self.export_dir / f"connections_{session_id}_{timestamp}.csv"

        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Source', 'Target', 'Path', 'Path Count', 'Depth'])
            
            for conn in results.get('connections_found', []):
                path_str = ' -> '.join(conn['path'])
                writer.writerow([
                    conn['source'],
                    conn['target'],
                    path_str,
                    conn['path_count'],
                    conn.get('found_at_depth', 'unknown')
                ])

        print(f"âœ… CSV saved: {csv_file}")
        return str(csv_file)

    def export_to_json(self, results: Dict[str, Any], session_id: str) -> str:
        """Export to JSON format - connections only (NO visited data)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = self.export_dir / f"connections_{session_id}_{timestamp}.json"

        # Clean export: only include relevant connection data, NOT the massive visited dicts
        clean_results = {
            'status': results.get('status'),
            'connections_found': results.get('connections_found', []),
            'total_addresses_examined': results.get('total_addresses_examined', 0),
            'search_depth': results.get('search_depth', 0),
            'block_range': results.get('block_range'),
            'timestamp': timestamp
        }

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(clean_results, f, indent=2)

        print(f"âœ… JSON saved: {json_file}")
        return str(json_file)

    def export_both(self, results: Dict[str, Any], session_id: str) -> Tuple[str, str]:
        """Export to both formats"""
        csv_path = self.export_to_csv(results, session_id)
        json_path = self.export_to_json(results, session_id)
        return csv_path, json_path

    def initialize_incremental_export(self, session_id: str) -> Tuple[str, str]:
        """Initialize export files for incremental updates"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = self.export_dir / f"connections_{session_id}_{timestamp}.csv"
        json_file = self.export_dir / f"connections_{session_id}_{timestamp}.json"

        # Create CSV file with header
        csv_f = open(csv_file, 'w', newline='', encoding='utf-8')
        csv_writer = csv.writer(csv_f)
        csv_writer.writerow(['Source', 'Target', 'Path', 'Path Count', 'Depth'])

        # Initialize JSON structure
        json_data = {
            'status': 'searching',
            'connections_found': [],
            'total_addresses_examined': 0,
            'search_depth': 0,
            'block_range': None,
            'timestamp': timestamp
        }

        # Save initial JSON
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)

        # Store active export info
        self._active_exports[session_id] = {
            'csv_path': str(csv_file),
            'json_path': str(json_file),
            'csv_file': csv_f,
            'csv_writer': csv_writer,
            'json_data': json_data,
            'timestamp': timestamp
        }

        print(f"📝 Initialized incremental exports: {csv_file.name}, {json_file.name}")
        return str(csv_file), str(json_file)

    def append_connection(self, session_id: str, connection: Dict[str, Any], 
                          total_addresses_examined: int = 0, search_depth: int = 0,
                          block_range: Any = None, status: str = 'searching'):
        """Append a new connection to the active export files"""
        if session_id not in self._active_exports:
            print(f"⚠️  Warning: No active export for session {session_id}, initializing...")
            self.initialize_incremental_export(session_id)

        export_info = self._active_exports[session_id]

        # Append to CSV
        path_str = ' -> '.join(connection['path'])
        export_info['csv_writer'].writerow([
            connection['source'],
            connection['target'],
            path_str,
            connection['path_count'],
            connection.get('found_at_depth', 'unknown')
        ])
        export_info['csv_file'].flush()  # Ensure it's written to disk

        # Update JSON data
        export_info['json_data']['connections_found'].append(connection)
        export_info['json_data']['total_addresses_examined'] = total_addresses_examined
        export_info['json_data']['search_depth'] = search_depth
        export_info['json_data']['block_range'] = block_range
        export_info['json_data']['status'] = status

        # Write updated JSON
        with open(export_info['json_path'], 'w', encoding='utf-8') as f:
            json.dump(export_info['json_data'], f, indent=2)

        print(f"  ✓ Updated exports: {len(export_info['json_data']['connections_found'])} connection(s)")

    def finalize_incremental_export(self, session_id: str, results: Dict[str, Any]):
        """Finalize the incremental export with complete results"""
        if session_id not in self._active_exports:
            # Fallback to regular export
            return self.export_both(results, session_id)

        export_info = self._active_exports[session_id]

        # Close CSV file
        export_info['csv_file'].close()

        # Final JSON update
        export_info['json_data'].update({
            'status': results.get('status', 'completed'),
            'connections_found': results.get('connections_found', []),
            'total_addresses_examined': results.get('total_addresses_examined', 0),
            'search_depth': results.get('search_depth', 0),
            'block_range': results.get('block_range')
        })

        # Write final JSON
        with open(export_info['json_path'], 'w', encoding='utf-8') as f:
            json.dump(export_info['json_data'], f, indent=2)

        csv_path = export_info['csv_path']
        json_path = export_info['json_path']

        # Clean up
        del self._active_exports[session_id]

        print(f"✅ Finalized exports: {csv_path}, {json_path}")
        return csv_path, json_path