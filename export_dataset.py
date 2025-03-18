#!/usr/bin/env python3
import argparse
import json
import csv
import sys
import os
from pathlib import Path

def export_to_csv(dataset_file, output_file, include_image_paths=False):
    """Export dataset from JSON to CSV format.
    
    Args:
        dataset_file: Path to the dataset JSON file
        output_file: Path to save the CSV file
        include_image_paths: Whether to include image paths in the CSV
    """
    # Load dataset
    with open(dataset_file, 'r') as f:
        dataset = json.load(f)
    
    if not dataset.get('items'):
        print("Error: Dataset contains no items.")
        return
    
    # Setup CSV field names
    fieldnames = ['id']
    if include_image_paths:
        fieldnames.append('image_path')
    
    # Add all shared attributes to the fieldnames
    shared_attributes = []
    if dataset.get('attributes'):
        shared_attributes = [attr['name'] for attr in dataset['attributes'] if attr.get('name')]
        fieldnames.extend(shared_attributes)
    
    # Add notes field
    fieldnames.append('notes')
    
    # Write CSV file
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in dataset['items']:
            row = {'id': item['id']}
            
            if include_image_paths:
                row['image_path'] = item.get('image', '')
            
            # Add all attribute values (will be empty strings if not present)
            for attr_name in shared_attributes:
                row[attr_name] = item.get('attribute_values', {}).get(attr_name, '')
            
            row['notes'] = item.get('notes', '')
            writer.writerow(row)
    
    print(f"Exported {len(dataset['items'])} items to {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Export dataset to CSV format')
    parser.add_argument('--dataset-file', default='./dataset/dataset_data.json', 
                        help='Path to the dataset JSON file')
    parser.add_argument('--output-file', default='./dataset_export.csv',
                        help='Path to save the CSV file')
    parser.add_argument('--include-image-paths', action='store_true',
                        help='Include image paths in the CSV')
    args = parser.parse_args()
    
    # Validate input file
    dataset_path = Path(args.dataset_file)
    if not dataset_path.exists():
        print(f"Error: Dataset file not found: {args.dataset_file}")
        sys.exit(1)
    
    # Export to CSV
    export_to_csv(args.dataset_file, args.output_file, args.include_image_paths)

if __name__ == "__main__":
    main() 