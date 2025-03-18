# Dataset Builder

A tool for creating and managing image datasets with custom attributes. Features:

- Scan image folders automatically
- View/edit dataset in web interface
- Add shared attributes across all items
- Edit attribute values per item
- Search/filter by ID or attributes
- Export to CSV or SQLite

## Setup

**Prerequisites:**
- Python 3.6+
- Image folder

**Quick Start:**
```bash
# Basic usage
python3 dataset_builder.py --image-dir ./images --output-dir ./my_dataset

# Then open in browser
http://localhost:8000
```

## Command Options

**Dataset Builder:**
```
--image-dir DIR     Directory with images (required)
--output-dir DIR    Output directory (required)
--port PORT         HTTP server port (default: 8000)
--scan-only         Only scan images without starting server
--export-db PATH    Export to SQLite database
```

**Export to CSV:**
```
python3 export_dataset.py --dataset-file ./my_dataset/dataset_data.json --output-file export.csv
```

Options:
```
--dataset-file PATH   Path to dataset JSON (default: ./dataset/dataset_data.json)
--output-file PATH    CSV output path (default: ./dataset_export.csv)
--include-image-paths Include image paths in CSV
```

## Working with Attributes

1. Click "Add Attribute" in sidebar
2. Enter attribute name and optional description
3. Add values per item in main view
4. Click "Save Changes" to persist

## Export Options

**CSV (for spreadsheets):**
```bash
python3 export_dataset.py --dataset-file ./my_dataset/dataset_data.json --output-file export.csv
```

**SQLite Database:**
```bash
python3 dataset_builder.py --image-dir ./images --output-dir ./my_dataset --export-db ./database.sqlite
```

Database schema:
- `items`: id, image_path, notes
- `attributes`: name, description
- `attribute_values`: item_id, attribute_name, value

## Customization

To customize ID extraction from filenames, modify `_extract_id_from_filename()` method:

```python
def _extract_id_from_filename(self, filename: str) -> str:
    """Extract ID from filename."""
    # Extract numbers from filenames like 'product_123.jpg'
    match = re.search(r'_(\d+)', filename)
    if match:
        return match.group(1)
    # Fallback to filename without extension
    return Path(filename).stem
```

## Typical Workflow

1. Put images in folder
2. Run tool to scan images and launch viewer
3. Define shared attributes
4. Enter attribute values for each item
5. Save changes
6. Export to CSV or database 