# Dataset Builder

A simple tool to create and manage a dataset with images and custom attributes. This tool allows you to:

1. Automatically scan a folder of images
2. View images in a clean web interface
3. Add shared attributes across all items
4. Enter values for each attribute per item
5. Search and filter your dataset by ID or attributes
6. Save changes for later use
7. Export to CSV for use in spreadsheets
8. Export directly to databases

## Setup

### Prerequisites

- Python 3.6 or higher
- A folder containing your images

No external dependencies are required beyond the Python standard library.

### Quick Start

1. Place your images in a folder (e.g., `./images`)
2. Run the tool:

```bash
python3 dataset_builder.py --image-dir ./images --output-dir ./my_dataset
```

3. Open your browser to http://localhost:8000 to view and edit your dataset

## Usage

### Command Line Options

```
python3 dataset_builder.py --help
```

Available options:
- `--image-dir`: Directory containing your images (default: ./images)
- `--output-dir`: Output directory for the dataset (default: ./dataset)
- `--port`: Port for the HTTP server (default: 8000)
- `--scan-only`: Only scan images, don't run the server
- `--export-db`: Export to SQLite database (provide path for database file)

### Working with IDs

By default, the tool uses the filename (without extension) as the ID for each item. If your filenames include IDs in a specific format, you can customize the ID extraction by modifying the `_extract_id_from_filename` method in the code.

For example, if your images are named like `product_123.jpg` and you want to extract just the number:

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

### Working with Shared Attributes

The left sidebar allows you to define attributes that apply to all items in your dataset:

1. Click "Add Attribute" in the sidebar to create a new shared attribute
2. Enter the attribute name and an optional description
3. For each item, you can now enter values for this attribute
4. All items will display the same attributes, maintaining consistency

You can remove an attribute by clicking the "Remove" button next to it. This will remove the attribute and its values from all items.

### Adding Attribute Values

1. For each item, enter values for any of the shared attributes
2. The changes will be highlighted but not saved until you click "Save All Changes"
3. Leave a value empty if it doesn't apply to that item

### Searching and Filtering

You can search for items by:
- ID
- Attribute values
- Notes

Enter a search term in the search box at the top of the page and click "Search" to filter the items.

### Exporting Your Dataset

#### To CSV (for Google Sheets or Excel)

Use the included export utility to convert your dataset to CSV:

```bash
python3 export_dataset.py --dataset-file ./my_dataset/dataset_data.json --output-file my_dataset.csv
```

Options:
- `--dataset-file`: Path to the dataset JSON file
- `--output-file`: Path to save the CSV file
- `--include-image-paths`: Include image paths in the CSV (optional)

#### To SQLite Database

Export directly to an SQLite database:

```bash
python3 dataset_builder.py --image-dir ./images --output-dir ./my_dataset --export-db ./my_database.sqlite
```

This will create a database with three tables:
- `items`: Contains id, image_path, and notes
- `attributes`: Contains the shared attribute definitions (name, description)
- `attribute_values`: Contains item_id, attribute_name, value relations

#### Programmatic Access

The dataset is stored as JSON in the output directory (`dataset_data.json`). This can be easily converted to other formats or imported into a database.

Example of reading the dataset in Python:

```python
import json

with open('dataset/dataset_data.json', 'r') as f:
    dataset = json.load(f)

# Access your data
for item in dataset['items']:
    print(f"ID: {item['id']}")
    print(f"Attribute Values: {item.get('attribute_values', {})}")
    print(f"Notes: {item.get('notes', '')}")

# Access shared attributes
for attr in dataset.get('attributes', []):
    print(f"Attribute: {attr['name']} ({attr.get('description', '')})")
```

## Workflow

A typical workflow with this tool:

1. Place your images in the images folder
2. Run the tool to scan images and launch the viewer
3. Define shared attributes in the sidebar
4. Enter attribute values for each item
5. Add notes as needed
6. Save your changes
7. When complete, export to CSV, database, or use the JSON directly
8. Import the data into your application or database

## Customization

The tool is designed to be simple and easily customizable:

- Modify the HTML template in `generate_html()` to change the UI
- Add additional fields to the data structure in `scan_images()`
- Implement custom ID extraction in `_extract_id_from_filename()`
- Add support for additional database types in `export_to_database()` 