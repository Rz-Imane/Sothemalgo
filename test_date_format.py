#!/usr/bin/env python3
"""
Test script to reproduce and check for date formatting issues
"""

from datetime import datetime
import sys
import os

# Add current directory to path
sys.path.append('.')

def test_date_parsing():
    """Test various date formats that might cause issues"""
    print("=== Testing Date Parsing ===")
    
    test_dates = [
        "2025-07-01",    # ISO format (correct)
        "01/07/2025",    # DD/MM/YYYY format 
        "07/01/2025",    # MM/DD/YYYY format (could cause confusion)
        "01/07/25",      # DD/MM/YY format
        "2025-7-1",      # ISO without leading zeros
    ]
    
    for date_str in test_dates:
        print(f"\nTesting date string: '{date_str}'")
        
        # Test ISO format first
        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
            print(f"  ✓ Parsed as ISO: {parsed_date.strftime('%Y-%m-%d')}")
            continue
        except ValueError:
            pass
            
        # Test DD/MM/YYYY format
        try:
            parsed_date = datetime.strptime(date_str, "%d/%m/%Y")
            print(f"  ✓ Parsed as DD/MM/YYYY: {parsed_date.strftime('%Y-%m-%d')}")
            continue
        except ValueError:
            pass
            
        # Test DD/MM/YY format
        try:
            parsed_date = datetime.strptime(date_str, "%d/%m/%y")
            print(f"  ✓ Parsed as DD/MM/YY: {parsed_date.strftime('%Y-%m-%d')}")
            continue
        except ValueError:
            pass
            
        print(f"  ✗ Could not parse date: {date_str}")

def test_problematic_format():
    """Test what could cause '07/072025' format"""
    print("\n=== Testing Problematic Format Generation ===")
    
    test_date = datetime(2025, 7, 1)
    
    # Different strftime formats that could cause issues
    formats_to_test = [
        "%d/%m/%Y",      # Should be 01/07/2025
        "%m/%d/%Y",      # Should be 07/01/2025  
        "%d/%m%Y",       # Could be 01/072025 (missing slash)
        "%m/%d%Y",       # Could be 07/012025 (missing slash)
        "%d/%Y%m",       # Could be 01/202507 (wrong order)
        "%m/%Y%d",       # Could be 07/202501 (wrong order)
        "%d/%m%y",       # Should be 01/0725
        "%d%m/%Y",       # Could be 0107/2025
        "%m%d/%Y",       # Could be 0701/2025
    ]
    
    for fmt in formats_to_test:
        try:
            result = test_date.strftime(fmt)
            print(f"  Format '{fmt}' produces: '{result}'")
            if "072025" in result:
                print(f"    ⚠️  FOUND PROBLEMATIC FORMAT!")
        except Exception as e:
            print(f"  Format '{fmt}' failed: {e}")

def check_current_output():
    """Check current output files for date format issues"""
    print("\n=== Checking Current Output Files ===")
    
    output_files = [
        "uploads/besoins_groupes_output_web.txt",
        "test_besoins_groupes_output_new.txt"
    ]
    
    for file_path in output_files:
        if os.path.exists(file_path):
            print(f"\nChecking file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for i, line in enumerate(lines[:50], 1):  # Check first 50 lines
                    if "2025" in line:
                        print(f"  Line {i}: {line.strip()}")
                        # Check for problematic patterns
                        if "072025" in line or "/2025" in line.replace("-", "/"):
                            print(f"    ⚠️  Potential date format issue detected!")
        else:
            print(f"File not found: {file_path}")

if __name__ == "__main__":
    test_date_parsing()
    test_problematic_format()
    check_current_output()
