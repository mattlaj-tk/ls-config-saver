#!/usr/bin/env python3
import os
import re
import json
import shutil
import argparse
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import time

class DatasetHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, dataset_builder=None, **kwargs):
        self.dataset_builder = dataset_builder
        try:
            super().__init__(*args, **kwargs)
        except BrokenPipeError:
            # Client disconnected, just ignore
            pass
        except ConnectionResetError:
            # Connection reset by client
            pass
        except Exception as e:
            print(f"Error handling HTTP request: {e}")

    def handle(self):
        try:
            super().handle()
        except BrokenPipeError:
            # Client disconnected, just ignore
            pass
        except ConnectionResetError:
            # Connection reset by client
            pass
        except Exception as e:
            print(f"Error handling HTTP connection: {e}")

    def handle_one_request(self):
        try:
            return super().handle_one_request()
        except BrokenPipeError:
            # Client disconnected, just ignore
            self.close_connection = True
        except ConnectionResetError:
            # Connection reset by client
            self.close_connection = True
        except Exception as e:
            print(f"Error handling HTTP request: {e}")
            self.close_connection = True

    def send_uncached_response(self, code, content_type, content):
        """Helper method to send a response with cache-control headers."""
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        
        if isinstance(content, str):
            self.wfile.write(content.encode('utf-8'))
        elif isinstance(content, bytes):
            self.wfile.write(content)
        elif content is not None:
            self.wfile.write(str(content).encode('utf-8'))
    
    def do_GET(self):
        """Handle GET requests with better error handling."""
        try:
            # Extract the path without query parameters
            base_path = self.path.split('?')[0] if '?' in self.path else self.path
            
            # Handle ping request for restart detection
            if '?ping=' in self.path:
                self.send_uncached_response(200, 'text/plain', 'OK')
                return
            
            # Ensure dataset_viewer.html gets served properly
            if base_path == '/dataset_viewer.html':
                try:
                    html_path = Path(self.dataset_builder.output_dir) / 'dataset_viewer.html'
                    if html_path.exists():
                        with open(html_path, 'rb') as f:
                            content = f.read()
                            self.send_uncached_response(200, 'text/html', content)
                            print(f"Served dataset_viewer.html")
                    else:
                        print(f"Warning: dataset_viewer.html not found at {html_path}")
                        error_html = "<html><body><h1>Error: Dataset viewer not found</h1><p>Try restarting the server.</p></body></html>"
                        self.send_uncached_response(404, 'text/html', error_html)
                except Exception as e:
                    print(f"Error serving dataset_viewer.html: {e}")
                    self.send_uncached_response(500, 'text/html', "<html><body><h1>Error loading page</h1></body></html>")
                return
            
            # For all other requests, use the standard handler
            super().do_GET()
        except BrokenPipeError:
            # Client disconnected, just ignore
            pass
        except ConnectionResetError:
            # Connection reset by client
            pass
        except Exception as e:
            print(f"Error during GET request: {e}")
            try:
                self.send_error(500, f"Internal server error")
            except:
                pass

    def do_POST(self):
        """Handle POST requests for saving data and restarting server."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
            
            if self.path == '/save':
                try:
                    data = json.loads(post_data)
                    self.dataset_builder.dataset = data
                    self.dataset_builder._save_dataset()
                    self.send_uncached_response(200, 'application/json', '{"status": "success"}')
                except Exception as e:
                    print(f"Error saving data: {e}")
                    error_data = json.dumps({
                        'status': 'error',
                        'message': str(e)
                    })
                    self.send_uncached_response(500, 'application/json', error_data)
            elif self.path == '/restart':
                try:
                    print("Received restart request from client...")
                    
                    # Save any pending changes first
                    try:
                        data = json.loads(post_data)
                        self.dataset_builder.dataset = data
                        self.dataset_builder._save_dataset()
                        print("Data saved during restart request")
                    except Exception as e:
                        print(f"Warning: Could not save data during restart: {e}")
                    
                    # Send success response before restarting
                    response_data = json.dumps({
                        'status': 'success', 
                        'message': 'Server restarting...'
                    })
                    self.send_uncached_response(200, 'application/json', response_data)
                    
                    # Create a restart flag file to signal to the main process
                    # Make sure the flag is written and flushed to disk
                    restart_flag_file = Path(self.dataset_builder.output_dir) / ".restart_needed"
                    try:
                        with open(restart_flag_file, 'w') as f:
                            f.write(str(time.time()))
                            f.flush()
                            os.fsync(f.fileno())  # Ensure it's written to disk
                        print(f"Created restart flag file: {restart_flag_file}")
                    except Exception as e:
                        print(f"Warning: Could not create restart flag file: {e}")
                    
                    # Make sure the flag file exists
                    if not restart_flag_file.exists():
                        print("WARNING: Restart flag file was not created properly!")
                        try:
                            # Try one more time with a simpler approach
                            with open(restart_flag_file, 'w') as f:
                                f.write('restart')
                            print("Retry creating restart flag succeeded")
                        except:
                            print("Failed to create restart flag file even on retry")
                    
                    # Schedule server shutdown
                    def shutdown_server():
                        try:
                            # Give time for the browser to receive the response
                            time.sleep(1)
                            print("Shutting down server for restart...")
                            # We don't want to call self.server.shutdown() directly
                            # as it will block until the server is done serving requests
                            # Instead, we'll use a thread to shutdown the server
                            threading.Thread(target=self.server.shutdown, daemon=True).start()
                        except Exception as e:
                            print(f"Error during server shutdown: {e}")
                    
                    # Start shutdown thread as daemon so it doesn't block process exit
                    shutdown_thread = threading.Thread(target=shutdown_server, daemon=True)
                    shutdown_thread.start()
                except Exception as e:
                    print(f"Error processing restart request: {e}")
                    error_data = json.dumps({
                        'status': 'error',
                        'message': str(e)
                    })
                    self.send_uncached_response(500, 'application/json', error_data)
            elif self.path == '/refresh':
                try:
                    print("Processing refresh request...")
                    
                    # First save the dataset to ensure we don't lose any changes
                    try:
                        if content_length > 0:
                            data = json.loads(post_data)
                            self.dataset_builder.dataset = data
                            self.dataset_builder._save_dataset()
                    except Exception as e:
                        print(f"Warning: Could not save data during refresh: {e}")
                    
                    # Scan for images
                    self.dataset_builder.scan_images()
                    
                    # Regenerate HTML to ensure it's up-to-date
                    try:
                        self.dataset_builder.generate_html()
                    except Exception as e:
                        print(f"Warning: Could not regenerate HTML during refresh: {e}")
                    
                    # Send the updated dataset as response
                    response_data = json.dumps({
                        'status': 'success',
                        'items': self.dataset_builder.dataset['items'],
                        'last_updated': self.dataset_builder.dataset['last_updated'],
                        'message': f"Found {len(self.dataset_builder.dataset['items'])} items"
                    })
                    
                    self.send_uncached_response(200, 'application/json', response_data)
                    print(f"Refresh complete. Found {len(self.dataset_builder.dataset['items'])} items.")
                except Exception as e:
                    print(f"Error processing refresh request: {e}")
                    error_data = json.dumps({
                        'status': 'error',
                        'message': str(e)
                    })
                    self.send_uncached_response(500, 'application/json', error_data)
            else:
                self.send_response(404)
                self.end_headers()
        except BrokenPipeError:
            # Client disconnected, just ignore
            pass
        except ConnectionResetError:
            # Connection reset by client
            pass
        except Exception as e:
            print(f"Error in POST request: {e}")
            try:
                self.send_response(500)
                self.end_headers()
            except:
                pass

class DatasetBuilder:
    """A simple tool to create a dataset from images and allow manual attribute editing."""
    
    def __init__(self, image_dir: str, output_dir: str, data_file: str = 'dataset_data.json'):
        """Initialize the dataset builder.
        
        Args:
            image_dir: Directory containing the images
            output_dir: Directory to store the HTML and dataset files
            data_file: Name of the JSON file to store dataset
        """
        self.image_dir = Path(image_dir)
        self.output_dir = Path(output_dir)
        self.data_file = self.output_dir / data_file
        self.output_html = self.output_dir / 'dataset_viewer.html'
        self.image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create images directory within output
        self.output_images_dir = self.output_dir / 'images'
        self.output_images_dir.mkdir(exist_ok=True)
        
        # Load existing data if available
        self.dataset = self._load_existing_data()
    
    def _load_existing_data(self) -> Dict:
        """Load existing dataset if available, otherwise return empty dict."""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r') as f:
                    dataset = json.load(f)
                    
                    # Ensure dataset has all required fields
                    if 'items' not in dataset:
                        dataset['items'] = []
                    if 'attributes' not in dataset:
                        dataset['attributes'] = []
                    if 'last_updated' not in dataset:
                        dataset['last_updated'] = ""
                    
                    # Ensure 'ID' is the first attribute
                    dataset['attributes'] = [attr for attr in dataset['attributes'] if attr['name'] != 'ID']
                    dataset['attributes'].insert(0, {
                        'name': 'ID',
                        'description': '',
                        'readonly': True
                    })
                    
                    # Make sure all items have ID in their attribute_values
                    for item in dataset['items']:
                        if 'attribute_values' not in item:
                            item['attribute_values'] = {}
                        item['attribute_values']['ID'] = item['id']
                        
                    return dataset
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {self.data_file}. Starting with empty dataset.")
        return {
            "items": [], 
            "attributes": [{
                'name': 'ID',
                'description': '',
                'readonly': True
            }], 
            "last_updated": ""
        }
    
    def _extract_id_from_filename(self, filename: str) -> str:
        """Extract ID from filename. Default implementation assumes filename is the ID.
        
        Override this method for custom ID extraction logic.
        """
        # Default implementation: Use filename without extension as ID
        return Path(filename).stem
    
    def scan_images(self):
        """Scan the image directory and update the dataset."""
        # Get all image files
        image_files = []
        for ext in self.image_exts:
            image_files.extend(list(self.image_dir.glob(f'*{ext}')))
        
        print(f"Scanning for images in {self.image_dir}")
        
        # Copy images to output directory and update dataset
        existing_ids = {item['id'] for item in self.dataset['items']}
        for img_path in image_files:
            item_id = self._extract_id_from_filename(img_path.name)
            
            # Copy image to output directory
            dest_path = self.output_images_dir / img_path.name
            if not dest_path.exists():
                shutil.copy2(img_path, dest_path)
                print(f"Copied image: {img_path.name} to {dest_path}")
            
            # Add to dataset if not already present
            if item_id not in existing_ids:
                self.dataset['items'].append({
                    'id': item_id,
                    'image': f'images/{img_path.name}',
                    'attribute_values': {
                        'ID': item_id  # Set the ID attribute value
                    },
                    'notes': ''
                })
                existing_ids.add(item_id)
                print(f"Added new item: {item_id}")
            else:
                # Update existing item's id attribute value
                for item in self.dataset['items']:
                    if item['id'] == item_id:
                        if 'attribute_values' not in item:
                            item['attribute_values'] = {}
                        item['attribute_values']['ID'] = item_id
                        break
        
        # Update timestamp
        self.dataset['last_updated'] = datetime.now().isoformat()
        
        # Save updated dataset
        self._save_dataset()
        
        print(f"Scanned {len(image_files)} images. Dataset now contains {len(self.dataset['items'])} items.")
    
    def _save_dataset(self):
        """Save dataset to JSON file."""
        try:
            # Ensure the output directory exists
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, 'w') as f:
                json.dump(self.dataset, f, indent=2)
            print(f"Dataset saved to {self.data_file}")
        except Exception as e:
            print(f"Error saving dataset to {self.data_file}: {e}")
            raise
    
    def export_to_database(self, db_config=None):
        """Export dataset to a database."""
        if db_config is None:
            print("Database configuration is required")
            return False
        
        db_type = db_config.get('type', '').lower()
        
        print(f"Exporting dataset to {db_type} database...")
        
        # Example implementation for SQLite:
        if db_type == 'sqlite':
            try:
                import sqlite3
                db_path = db_config.get('path')
                if not db_path:
                    print("Database path is required for SQLite")
                    return False
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Create tables if they don't exist
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS items (
                        id TEXT PRIMARY KEY,
                        image_path TEXT,
                        notes TEXT
                    )
                ''')
                
                # Create attributes table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS attributes (
                        name TEXT PRIMARY KEY,
                        description TEXT
                    )
                ''')
                
                # Create attribute values table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS attribute_values (
                        item_id TEXT,
                        attribute_name TEXT,
                        value TEXT,
                        PRIMARY KEY (item_id, attribute_name),
                        FOREIGN KEY (item_id) REFERENCES items(id),
                        FOREIGN KEY (attribute_name) REFERENCES attributes(name)
                    )
                ''')
                
                # Insert items
                for item in self.dataset['items']:
                    cursor.execute(
                        "INSERT OR REPLACE INTO items (id, image_path, notes) VALUES (?, ?, ?)",
                        (item['id'], item.get('image', ''), item.get('notes', ''))
                    )
                
                # Insert attributes
                for attr in self.dataset['attributes']:
                    cursor.execute(
                        "INSERT OR REPLACE INTO attributes (name, description) VALUES (?, ?)",
                        (attr['name'], attr.get('description', ''))
                    )
                    
                # Insert attribute values
                for item in self.dataset['items']:
                    # Ensure ID attribute is always set
                    if 'attribute_values' not in item:
                        item['attribute_values'] = {}
                    item['attribute_values']['ID'] = item['id']
                    
                    for attr_name, value in item.get('attribute_values', {}).items():
                        cursor.execute(
                            "INSERT OR REPLACE INTO attribute_values (item_id, attribute_name, value) VALUES (?, ?, ?)",
                            (item['id'], attr_name, value)
                        )
                
                conn.commit()
                conn.close()
                print(f"Exported {len(self.dataset['items'])} items to SQLite database at {db_path}")
                return True
                
            except ImportError:
                print("SQLite3 module is required but it's part of Python standard library")
                return False
            except Exception as e:
                print(f"Error exporting to SQLite database: {e}")
                return False
        
        # Add more database implementations as needed
        
        return False
    
    def generate_html(self):
        """Generate HTML viewer/editor for the dataset."""
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dataset Viewer</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            color: #333;
        }
        .header {
            background-color: #f8f9fa;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .controls {
            margin-bottom: 20px;
        }
        .container {
            display: flex;
            gap: 20px;
        }
        .sidebar {
            width: 300px;
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            height: fit-content;
            position: sticky;
            top: 20px;
        }
        .item-container {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            flex: 1;
        }
        .item-card {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            width: 300px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            background-color: white;
            position: relative;
        }
        .item-image {
            width: 100%;
            height: 200px;
            object-fit: contain;
            border-radius: 5px;
            margin-bottom: 10px;
            background-color: #f8f9fa;
        }
        .item-details {
            margin-bottom: 15px;
        }
        .item-id {
            font-weight: bold;
            color: #444;
            margin-bottom: 5px;
        }
        label {
            display: block;
            margin-top: 8px;
            font-weight: bold;
            font-size: 0.9em;
            color: #555;
        }
        input[type="text"], textarea {
            width: calc(100% - 16px);
            padding: 8px;
            margin-top: 4px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 0.9em;
        }
        textarea {
            height: 60px;
            resize: vertical;
        }
        .item-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .attribute-control {
            margin-bottom: 15px;
        }
        .attribute-row {
            display: flex;
            margin-bottom: 8px;
        }
        .attribute-row input {
            flex: 1;
            margin-right: 5px;
        }
        .shared-attribute-row {
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #eee;
        }
        .highlight-new {
            animation: highlight-fade 3s ease;
            border-left: 3px solid #28a745;
            padding-left: 10px;
        }
        @keyframes highlight-fade {
            0% { background-color: rgba(40, 167, 69, 0.2); }
            100% { background-color: transparent; }
        }
        .btn {
            padding: 5px 10px;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
        }
        .btn:hover {
            background-color: #45a049;
        }
        .btn-remove {
            background-color: #f44336;
        }
        .btn-remove:hover {
            background-color: #d32f2f;
        }
        .btn-save-all {
            margin-top: 20px;
            padding: 10px 15px;
            font-size: 1em;
        }
        .filter-box {
            margin-bottom: 15px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
        #searchInput {
            width: 300px;
            padding: 8px;
            margin-right: 10px;
        }
        .last-updated {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 10px;
        }
        .sidebar-header {
            font-size: 1.2em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }
        .hidden {
            display: none;
        }
        .attribute-section {
            margin-top: 15px;
        }
        .header-buttons {
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: background-color 0.3s;
        }
        .btn-primary {
            background-color: #007bff;
            color: white;
        }
        .btn-primary:hover {
            background-color: #0056b3;
        }
        .btn-save {
            background-color: #28a745;
            font-size: 1.1em; 
            padding: 10px 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }
        .btn-save:hover {
            background-color: #218838;
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        .btn-secondary {
            background-color: #6c757d;
            color: white;
        }
        .btn-secondary:hover {
            background-color: #545b62;
        }
        #status-message {
            display: none;
            padding: 10px;
            margin-top: 10px;
            border-radius: 4px;
            text-align: center;
        }
        .status-info {
            background-color: #cce5ff;
            color: #004085;
        }
        .readonly-attribute {
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 15px;
        }
        .readonly-attribute label {
            color: #495057;
            font-weight: bold;
        }
        .readonly-attribute .description {
            color: #6c757d;
            font-size: 0.9em;
            margin: 5px 0 0 0;
        }
        input[readonly] {
            background-color: #e9ecef;
            cursor: not-allowed;
        }
        .search-box {
            margin: 15px 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .search-box input {
            padding: 8px 12px;
            border: 1px solid #ccc;
            border-radius: 4px;
            flex-grow: 1;
            max-width: 400px;
        }
        
        .search-controls {
            display: flex;
            gap: 8px;
        }
        
        .status-message {
            margin-top: 10px;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Dataset Viewer</h1>
        <div class="header-buttons">
            <button class="btn btn-primary btn-save" onclick="saveAllChanges()">💾 Save Changes</button>
            <button class="btn btn-primary" onclick="refreshImages()" style="background-color: #17a2b8;">🔄 Refresh Images</button>
            <button class="btn btn-secondary" onclick="restartServer()">Restart Server</button>
        </div>
        <div id="status-message"></div>
        <div class="last-updated">Last updated: <span id="lastUpdated"></span></div>
        
        <div class="search-box">
            <input type="text" id="searchInput" placeholder="Search by ID or attribute values...">
            <div class="search-controls">
                <button class="btn btn-primary" onclick="searchItems()">Search</button>
                <button class="btn btn-secondary" onclick="clearSearch()">Clear</button>
            </div>
        </div>
        <div class="status-message">Showing <span id="itemCount">0</span> items</div>
    </div>
    
    <div class="container">
        <div class="sidebar">
            <div class="sidebar-header">Shared Attributes</div>
            <div id="sharedAttributes">
                <!-- Shared attributes will be generated here -->
            </div>
            <button class="btn" onclick="addSharedAttribute()">Add Attribute</button>
            <div class="attribute-control" style="margin-top: 20px;">
                <p class="note" style="font-size: 0.9em; color: #666;">
                    Note: After adding or editing attributes, click "Save Changes" at the top to save.
                </p>
            </div>
        </div>
        
        <div id="item-container" class="item-container">
            <!-- Items will be generated here -->
        </div>
    </div>

    <script>
        // Dataset
        const dataset = DATASET_JSON;
        let filteredItems = [...dataset.items];
        
        // Initialize the page
        document.addEventListener('DOMContentLoaded', function() {
            console.log('Page loaded');
            
            // Clean the URL if it has query parameters
            if (window.location.search && window.history && window.history.replaceState) {
                try {
                    // Get the base URL without query parameters
                    const baseUrl = window.location.href.split('?')[0];
                    console.log('Cleaning URL to:', baseUrl);
                    window.history.replaceState({}, document.title, baseUrl);
                } catch (e) {
                    console.warn('Could not clean URL:', e);
                }
            }
            
            // Initialize the UI
            renderSharedAttributes();
            renderItems(dataset.items);
            updateLastUpdated();
            updateItemCount();
        });
        
        function updateLastUpdated() {
            const lastUpdatedEl = document.getElementById('lastUpdated');
            if (lastUpdatedEl) {
                lastUpdatedEl.textContent = formatDate(dataset.last_updated);
            }
        }
        
        function updateItemCount() {
            const countEl = document.getElementById('itemCount');
            if (countEl) {
                countEl.textContent = filteredItems.length;
            }
        }
        
        function formatDate(dateString) {
            if (!dateString) return 'Never';
            const date = new Date(dateString);
            return date.toLocaleString();
        }
        
        function renderSharedAttributes() {
            const container = document.getElementById('sharedAttributes');
            container.innerHTML = '';
            
            if (!dataset.attributes) {
                dataset.attributes = [];
            }
            
            // Get all existing attribute names for duplicate checking
            const existingAttrNames = dataset.attributes.map(attr => attr.name.toLowerCase());
            
            dataset.attributes.forEach((attr, index) => {
                const attrElem = document.createElement('div');
                attrElem.className = 'shared-attribute-row';
                
                // Add highlight class for new attributes
                if (attr.isNew) {
                    attrElem.classList.add('highlight-new');
                    // Remove the isNew flag after it's been rendered once
                    setTimeout(() => { attr.isNew = false; }, 3000);
                }
                
                // Special handling for 'ID' attribute
                if (attr.name === 'ID') {
                    attrElem.innerHTML = `
                        <div class="readonly-attribute">
                            <label>ID</label>
                        </div>
                    `;
                } else {
                    const isNewLabel = attr.isNew ? '<span style="color: #28a745;"> (New - requires name)</span>' : '';
                    attrElem.innerHTML = `
                        <label>Attribute Name${isNewLabel}:</label>
                        <div style="display: flex; gap: 5px; margin-bottom: 5px;">
                            <input type="text" class="attr-name" value="${attr.name}" placeholder="Attribute name" style="flex-grow: 1;">
                            <button class="btn attr-save-btn" style="display: none;" onclick="saveAttribute(${index}, this)">Save</button>
                        </div>
                        <label>Description (optional):</label>
                        <input type="text" class="attr-description" value="${attr.description || ''}" placeholder="Description">
                        <button class="btn btn-remove" onclick="removeSharedAttribute(${index})">Remove</button>
                    `;
                    
                    // Add event listeners to show/hide save button based on input
                    setTimeout(() => {
                        const nameInput = attrElem.querySelector('.attr-name');
                        const saveBtn = attrElem.querySelector('.attr-save-btn');
                        
                        if (nameInput && saveBtn) {
                            const updateSaveButton = () => {
                                const name = nameInput.value.trim();
                                const isDuplicate = existingAttrNames.filter(
                                    (n, i) => n === name.toLowerCase() && i !== index
                                ).length > 0;
                                
                                if (name && !isDuplicate) {
                                    saveBtn.style.display = 'block';
                                    nameInput.style.borderColor = '';
                                } else if (isDuplicate) {
                                    saveBtn.style.display = 'none';
                                    nameInput.style.borderColor = 'red';
                                    nameInput.title = 'Attribute name must be unique';
                                } else {
                                    saveBtn.style.display = 'none';
                                    nameInput.style.borderColor = '';
                                }
                            };
                            
                            nameInput.addEventListener('input', updateSaveButton);
                            updateSaveButton(); // Initial check
                        }
                    }, 0);
                }
                container.appendChild(attrElem);
            });
        }
        
        function saveAttribute(index, button) {
            const attrRow = button.closest('.shared-attribute-row');
            const nameInput = attrRow.querySelector('.attr-name');
            const descInput = attrRow.querySelector('.attr-description');
            
            if (nameInput && nameInput.value.trim()) {
                const name = nameInput.value.trim();
                const description = descInput ? descInput.value.trim() : '';
                
                // Update the attribute
                dataset.attributes[index].name = name;
                dataset.attributes[index].description = description;
                
                // Show feedback
                button.textContent = '✓ Saved';
                button.style.backgroundColor = '#28a745';
                setTimeout(() => {
                    button.textContent = 'Save';
                    button.style.backgroundColor = '';
                }, 1000);
                
                // Update items with the new attribute
                dataset.items.forEach(item => {
                    if (!item.attribute_values) {
                        item.attribute_values = {};
                    }
                    // If this attribute didn't exist before in this item, initialize it
                    if (!(name in item.attribute_values)) {
                        item.attribute_values[name] = '';
                    }
                });
                
                // Re-render the items to show the new attribute
                renderItems(filteredItems);
            }
        }
        
        function addSharedAttribute() {
            if (!dataset.attributes) {
                dataset.attributes = [];
            }
            
            // Add new attribute after the 'ID' attribute with a flag for highlighting
            dataset.attributes.splice(1, 0, {
                name: "",
                description: "",
                isNew: true
            });
            
            renderSharedAttributes();
            showStatus('Attribute added! Fill in the name and click "Save Changes" to save.', 'info');
        }
        
        function removeSharedAttribute(index) {
            // Prevent removing the 'ID' attribute
            if (dataset.attributes[index].name === 'ID') {
                alert('The ID attribute cannot be removed as it is required.');
                return;
            }
            
            if (confirm('Are you sure you want to remove this attribute from all items?')) {
                const attrName = dataset.attributes[index].name;
                
                // Remove from shared attributes
                dataset.attributes.splice(index, 1);
                
                // Remove from all items
                if (attrName) {
                    dataset.items.forEach(item => {
                        if (item.attribute_values && item.attribute_values[attrName]) {
                            delete item.attribute_values[attrName];
                        }
                    });
                }
                
                renderSharedAttributes();
                renderItems(filteredItems);
            }
        }
        
        function renderItems(items) {
            const container = document.getElementById('item-container');
            container.innerHTML = '';
            
            items.forEach((item, index) => {
                const card = document.createElement('div');
                card.className = 'item-card';
                card.dataset.id = item.id;
                
                if (!item.attribute_values) {
                    item.attribute_values = {};
                }
                
                // Ensure ID attribute value is set
                item.attribute_values['ID'] = item.id;
                
                let attributesHtml = '';
                if (dataset.attributes && dataset.attributes.length > 0) {
                    attributesHtml = '<div class="attribute-section">';
                    dataset.attributes.forEach(attr => {
                        if (attr.name) {
                            const value = item.attribute_values[attr.name] || '';
                            if (attr.readonly) {
                                attributesHtml += `
                                <div class="attribute-row" data-name="${attr.name}">
                                    <label>${attr.name}:</label>
                                    <input type="text" class="attr-value" value="${value}" readonly>
                                </div>`;
                            } else {
                                attributesHtml += `
                                <div class="attribute-row" data-name="${attr.name}">
                                    <label>${attr.name}${attr.description ? ' (' + attr.description + ')' : ''}:</label>
                                    <input type="text" class="attr-value" value="${value}" placeholder="Value for ${attr.name}">
                                </div>`;
                            }
                        }
                    });
                    attributesHtml += '</div>';
                }
                
                card.innerHTML = `
                    <div class="item-header">
                        <div class="item-id">${item.id}</div>
                    </div>
                    <img src="${item.image}" alt="${item.id}" class="item-image">
                    <div class="item-details">
                        ${attributesHtml}
                        <label for="notes-${index}">Notes:</label>
                        <textarea id="notes-${index}" placeholder="Enter notes here...">${item.notes || ''}</textarea>
                    </div>
                `;
                
                container.appendChild(card);
            });
            
            if (items.length === 0) {
                container.innerHTML = '<p>No items found. Add images to get started.</p>';
            }
        }
        
        function saveAllChanges() {
            // Update shared attributes
            const sharedAttrElems = document.querySelectorAll('#sharedAttributes .shared-attribute-row');
            const idAttribute = dataset.attributes.find(attr => attr.name === 'ID');
            dataset.attributes = [idAttribute]; // Keep the ID attribute
            
            // Add other attributes
            sharedAttrElems.forEach(elem => {
                const nameInput = elem.querySelector('.attr-name');
                const descInput = elem.querySelector('.attr-description');
                if (nameInput && nameInput.value.trim() && nameInput.value.trim() !== 'ID') {
                    dataset.attributes.push({
                        name: nameInput.value.trim(),
                        description: descInput ? descInput.value.trim() : ''
                    });
                } else if (nameInput && !nameInput.value.trim() && nameInput.parentNode) {
                    // Visual indication that empty attributes will be removed
                    nameInput.style.borderColor = 'red';
                    nameInput.placeholder = 'Required - will be removed if empty';
                    setTimeout(() => {
                        nameInput.style.borderColor = '';
                        nameInput.placeholder = 'Attribute name';
                    }, 3000);
                }
            });
            
            // Update items
            const cards = document.querySelectorAll('.item-card');
            cards.forEach(card => {
                const itemId = card.dataset.id;
                const item = dataset.items.find(i => i.id === itemId);
                
                if (item) {
                    // Initialize attribute_values if it doesn't exist
                    if (!item.attribute_values) {
                        item.attribute_values = {};
                    }
                    
                    // Ensure ID attribute value is set
                    item.attribute_values['ID'] = item.id;
                    
                    // Update other attribute values
                    card.querySelectorAll('.attribute-row').forEach(row => {
                        const attrName = row.dataset.name;
                        if (attrName !== 'ID') {
                            const valueInput = row.querySelector('.attr-value');
                            if (valueInput) {
                                item.attribute_values[attrName] = valueInput.value.trim();
                            }
                        }
                    });
                    
                    // Update notes
                    const notesElem = card.querySelector('textarea');
                    if (notesElem) {
                        item.notes = notesElem.value.trim();
                    }
                }
            });
            
            // Update timestamp
            dataset.last_updated = new Date().toISOString();
            updateLastUpdated();
            
            // Send data to server
            fetch('/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(dataset)
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Server returned ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                showStatus('Changes saved successfully!', 'info');
                setTimeout(() => {
                    document.getElementById('status-message').style.display = 'none';
                }, 3000);
            })
            .catch(error => {
                showStatus('Error saving changes: ' + error.message, 'error');
            });
        }
        
        async function restartServer() {
            if (!confirm('This will save all changes and restart the server. The page will reload. Continue?')) {
                return;
            }
            
            showStatus('Saving changes and preparing to restart server...', 'info');
            
            try {
                // First, save all changes
                await new Promise((resolve, reject) => {
                    try {
                        // Update shared attributes
                        const sharedAttrElems = document.querySelectorAll('#sharedAttributes .shared-attribute-row');
                        const idAttribute = dataset.attributes.find(attr => attr.name === 'ID');
                        dataset.attributes = [idAttribute]; // Keep the ID attribute
                        
                        // Add other attributes
                        sharedAttrElems.forEach(elem => {
                            const nameInput = elem.querySelector('.attr-name');
                            const descInput = elem.querySelector('.attr-description');
                            if (nameInput && nameInput.value.trim() && nameInput.value.trim() !== 'ID') {
                                dataset.attributes.push({
                                    name: nameInput.value.trim(),
                                    description: descInput ? descInput.value.trim() : ''
                                });
                            }
                        });
                        
                        // Update timestamp
                        dataset.last_updated = new Date().toISOString();
                        resolve();
                    } catch (e) {
                        reject(e);
                    }
                });
                
                // Send restart request with saved data
                showStatus('Sending restart request to server...', 'info');
                
                const response = await fetch('/restart', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(dataset)
                });
                
                if (!response.ok) {
                    throw new Error('Server returned ' + response.status);
                }
                
                // Show the restart message
                showStatus('Server is restarting. Please wait...', 'info');
                
                // Create a simple countdown for UX
                let countdown = 10;
                const countdownTimer = setInterval(() => {
                    showStatus(`Server is restarting. Reloading in ${countdown} seconds...`, 'info');
                    countdown--;
                    if (countdown <= 0) {
                        clearInterval(countdownTimer);
                        showStatus('Reloading page now...', 'info');
                        
                        // Force reload after countdown
                        window.location.href = window.location.href.split('?')[0];
                    }
                }, 1000);
                
                // Start auto-reload attempts after a few seconds
                setTimeout(function attemptReload() {
                    fetch(window.location.href.split('?')[0] + '?ping=' + Date.now(), {
                        method: 'HEAD',
                        cache: 'no-cache'
                    })
                    .then(response => {
                        if (response.ok) {
                            clearInterval(countdownTimer);
                            showStatus('Server is back online! Reloading page...', 'info');
                            setTimeout(() => {
                                window.location.href = window.location.href.split('?')[0];
                            }, 500);
                        } else {
                            // Try again in a second if we haven't reached the countdown
                            if (countdown > 0) {
                                setTimeout(attemptReload, 1000);
                            }
                        }
                    })
                    .catch(error => {
                        // Server still restarting, try again in a second if we haven't reached the countdown
                        if (countdown > 0) {
                            setTimeout(attemptReload, 1000);
                        }
                    });
                }, 3000); // Start checking after 3 seconds
            } catch (error) {
                showStatus('Error during restart: ' + error.message, 'error');
                console.error('Restart error:', error);
                
                // Still try to reload after a longer delay
                setTimeout(() => {
                    window.location.href = window.location.href.split('?')[0];
                }, 10000);
            }
        }
        
        function showStatus(message, type) {
            const statusEl = document.getElementById('status-message');
            statusEl.textContent = message;
            statusEl.className = type === 'error' ? 'status-error' : 'status-info';
            statusEl.style.display = 'block';
        }
        
        function searchItems() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase().trim();
            
            if (!searchTerm) {
                filteredItems = [...dataset.items];
            } else {
                filteredItems = dataset.items.filter(item => {
                    // Search in item ID
                    if (item.id.toLowerCase().includes(searchTerm)) {
                        return true;
                    }
                    
                    // Search in attribute values
                    if (item.attribute_values) {
                        for (const [key, value] of Object.entries(item.attribute_values)) {
                            if (
                                value && 
                                value.toString().toLowerCase().includes(searchTerm) ||
                                key.toLowerCase().includes(searchTerm)
                            ) {
                                return true;
                            }
                        }
                    }
                    
                    // Search in notes
                    if (item.notes && item.notes.toLowerCase().includes(searchTerm)) {
                        return true;
                    }
                    
                    return false;
                });
            }
            
            renderItems(filteredItems);
            updateItemCount();
        }
        
        function clearSearch() {
            document.getElementById('searchInput').value = '';
            filteredItems = [...dataset.items];
            renderItems(filteredItems);
            updateItemCount();
        }
        
        async function refreshImages() {
            if (!confirm('This will scan for new images and refresh the dataset. Continue?')) {
                return;
            }
            
            showStatus('Refreshing images...', 'info');
            
            try {
                // First save any current changes
                await fetch('/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(dataset)
                });
                
                // Then request a refresh
                const response = await fetch('/refresh', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                if (!response.ok) {
                    throw new Error(`Server returned ${response.status}: ${response.statusText}`);
                }
                
                const data = await response.json();
                
                if (data.status !== 'success') {
                    throw new Error(data.message || 'Unknown error');
                }
                
                // Update the dataset with the refreshed data
                dataset.items = data.items;
                dataset.last_updated = data.last_updated;
                
                // Refresh the UI
                filteredItems = [...dataset.items];
                renderItems(filteredItems);
                updateLastUpdated();
                updateItemCount();
                
                showStatus(`Refresh complete! Found ${data.items.length} images.`, 'info');
            } catch (error) {
                console.error('Refresh error:', error);
                showStatus('Error refreshing images: ' + error.message, 'error');
            }
        }
    </script>
</body>
</html>
"""
        
        # Replace placeholders with actual data
        html_content = html_template.replace('DATASET_JSON', json.dumps(self.dataset))
        
        # Write HTML to file
        try:
            with open(self.output_html, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"HTML viewer generated at {self.output_html}")
            return self.output_html
        except Exception as e:
            print(f"Error writing HTML file to {self.output_html}: {e}")
            raise

    def run_server(self, port=8000):
        """Run the HTTP server."""
        # Convert all paths to absolute paths to avoid issues with current working directory
        self.image_dir = Path(self.image_dir).absolute()
        self.output_dir = Path(self.output_dir).absolute()
        self.data_file = Path(self.data_file).absolute()
        self.output_html = Path(self.output_html).absolute()
        self.output_images_dir = Path(self.output_images_dir).absolute()
        
        print(f"Image directory: {self.image_dir}")
        print(f"Output directory: {self.output_dir}")
        print(f"Dataset file: {self.data_file}")
        print(f"HTML viewer: {self.output_html}")
        
        # Make sure the directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.output_images_dir.mkdir(parents=True, exist_ok=True)
        
        # Clear any old restart flag
        restart_flag_file = Path(self.output_dir) / ".restart_needed"
        if restart_flag_file.exists():
            restart_flag_file.unlink()
        
        # Always generate HTML before starting the server
        self.generate_html()
        
        # Record the original directory before changing
        original_cwd = os.getcwd()
        
        # Change to output directory
        os.chdir(self.output_dir)
        print(f"Changed working directory to: {os.getcwd()}")
        
        def handler(*args, **kwargs):
            return DatasetHTTPHandler(*args, dataset_builder=self, **kwargs)
        
        # Set up graceful shutdown
        def signal_handler(signum, frame):
            print("\nShutting down server...")
            try:
                httpd.shutdown()
                httpd.server_close()
            except:
                pass
            # Change back to the original directory
            try:
                os.chdir(original_cwd)
                print(f"Changed back to original directory: {original_cwd}")
            except:
                pass
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Loop to restart server when needed
        retry_delay = 1  # Start with 1 second retry delay
        httpd = None
        check_restart_interval = 2  # Check for restart flag every 2 seconds
        
        # Start a thread to monitor for restart flag
        def check_restart_needed():
            while True:
                try:
                    # Check if restart flag exists
                    if restart_flag_file.exists():
                        print("Restart flag detected. Performing scan and regenerating HTML...")
                        
                        # Rescan images and regenerate HTML
                        try:
                            self.scan_images()
                        except Exception as e:
                            print(f"Warning: Error scanning images during restart: {e}")
                        
                        try:
                            self.generate_html()
                        except Exception as e:
                            print(f"Warning: Error generating HTML during restart: {e}")
                        
                        # DO NOT remove the flag file yet - we need it to persist
                        # until the server has fully shut down and detected the need to restart
                        print("Server will restart after shutdown...")
                        
                        # Signal the server to shutdown and restart
                        print("Triggering server shutdown for restart...")
                        
                        # Instead of directly calling httpd.shutdown(), we'll post a message
                        # to the main thread using a timer with a small delay
                        def trigger_shutdown():
                            if httpd:
                                try:
                                    print("Executing server shutdown for restart")
                                    httpd.shutdown()
                                except Exception as e:
                                    print(f"Error during shutdown for restart: {e}")
                        
                        # Use a timer with a small delay to allow this thread to finish first
                        restart_timer = threading.Timer(0.5, trigger_shutdown)
                        restart_timer.daemon = True
                        restart_timer.start()
                        
                        # Exit this thread
                        return
                except Exception as e:
                    print(f"Error checking restart flag: {e}")
                
                # Check less frequently to reduce CPU usage
                time.sleep(check_restart_interval)
        
        while True:
            try:
                # Start monitoring thread before starting server
                restart_monitor = threading.Thread(target=check_restart_needed, daemon=True)
                restart_monitor.start()
                
                # Create and start the server
                httpd = HTTPServer(("", port), handler)
                print(f"Server running at http://localhost:{port}/dataset_viewer.html")
                retry_delay = 1  # Reset retry delay on successful start
                httpd.serve_forever()
                
                # If we get here, the server has been shutdown
                print("Server has shutdown. Checking if restart is needed...")
                
                # Check if restart flag exists - if it does, this is a restart request
                restart_requested = restart_flag_file.exists()
                
                if restart_requested:
                    print("Restart flag found. Server will restart...")
                    
                    # Remove the flag file now that we've detected the restart request
                    try:
                        restart_flag_file.unlink()
                        print("Restart flag file removed after shutdown")
                    except Exception as e:
                        print(f"Warning: Could not remove restart flag file: {e}")
                    
                    # Brief pause before restarting
                    time.sleep(1)
                    
                    # Continue the loop to restart the server
                    print("Restarting server...")
                    continue
                else:
                    # Normal shutdown
                    print("No restart flag found. Normal shutdown detected. Exiting server.")
                    break
            except OSError as e:
                if e.errno == 98 or e.errno == 10048:  # Address already in use (Linux/Windows)
                    print(f"Port {port} is in use, trying {port + 1}")
                    port += 1
                else:
                    print(f"Error starting server: {e}")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)  # Exponential backoff up to 30 seconds
                    # Make sure HTML exists before retrying
                    if not self.output_html.exists():
                        print(f"HTML viewer file missing, regenerating at {self.output_html}...")
                        self.generate_html()
            except Exception as e:
                print(f"Server error: {e}")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)  # Exponential backoff up to 30 seconds
                # Make sure HTML exists before retrying
                if not self.output_html.exists():
                    print(f"HTML viewer file missing, regenerating at {self.output_html}...")
                    self.generate_html()
            finally:
                # Clean up if httpd was created
                if httpd is not None:
                    try:
                        httpd.server_close()
                    except:
                        pass
                    httpd = None


def main():
    parser = argparse.ArgumentParser(description="Dataset Builder Tool")
    parser.add_argument("--image-dir", required=True, help="Directory containing images")
    parser.add_argument("--output-dir", required=True, help="Directory to store dataset files")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    parser.add_argument("--scan-only", action="store_true", help="Only scan images and update dataset, don't start server")
    parser.add_argument("--export-db", help="Export to SQLite database file")
    
    args = parser.parse_args()
    
    builder = DatasetBuilder(args.image_dir, args.output_dir)
    builder.scan_images()
    
    if args.export_db:
        builder.export_to_database({'type': 'sqlite', 'path': args.export_db})
    elif not args.scan_only:
        builder.run_server(port=args.port)

if __name__ == "__main__":
    main() 