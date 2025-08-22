#!/usr/bin/env python3
"""
PDF Text Extractor for DL3000 Manuals

This script extracts text from the DL3000 programming manual and user guide
so we can understand the proper commands and setup for battery testing mode.
"""

import pdfplumber
import PyPDF2
import os
import re

def extract_text_with_pdfplumber(pdf_path):
    """Extract text using pdfplumber (better for complex layouts)"""
    text_content = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"Processing {pdf_path} - {len(pdf.pages)} pages")
            
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if text:
                        text_content.append(f"\n--- PAGE {i+1} ---\n")
                        text_content.append(text)
                except Exception as e:
                    print(f"Error extracting page {i+1}: {e}")
                    continue
                    
    except Exception as e:
        print(f"Error opening PDF with pdfplumber: {e}")
        return None
        
    return '\n'.join(text_content)

def extract_text_with_pypdf2(pdf_path):
    """Extract text using PyPDF2 (fallback method)"""
    text_content = []
    
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            print(f"Processing {pdf_path} - {len(pdf_reader.pages)} pages")
            
            for i, page in enumerate(pdf_reader.pages):
                try:
                    text = page.extract_text()
                    if text:
                        text_content.append(f"\n--- PAGE {i+1} ---\n")
                        text_content.append(text)
                except Exception as e:
                    print(f"Error extracting page {i+1}: {e}")
                    continue
                    
    except Exception as e:
        print(f"Error opening PDF with PyPDF2: {e}")
        return None
        
    return '\n'.join(text_content)

def find_battery_related_content(text):
    """Find sections related to battery testing"""
    if not text:
        return []
        
    # Split into sections
    sections = []
    
    # Look for battery-related keywords
    battery_keywords = [
        'battery', 'batt', 'cell', 'discharge', 'capacity',
        'function', 'mode', 'application', 'app', 'list',
        'sequence', 'protection', 'cutoff', 'voltage limit',
        'current limit', 'time limit', 'scpi command'
    ]
    
    lines = text.split('\n')
    current_section = []
    section_title = ""
    
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Check if this line contains battery-related keywords
        is_battery_related = any(keyword in line_lower for keyword in battery_keywords)
        
        # Look for section headers (lines in all caps or with specific formatting)
        is_header = (len(line.strip()) > 0 and 
                    (line.isupper() or 
                     line.startswith('Chapter') or 
                     line.startswith('Section') or
                     re.match(r'^\d+\.', line.strip())))
        
        if is_header and current_section:
            # Save previous section if it was battery-related
            section_text = '\n'.join(current_section)
            if any(keyword in section_text.lower() for keyword in battery_keywords):
                sections.append({
                    'title': section_title,
                    'content': section_text
                })
            current_section = []
            
        if is_header:
            section_title = line.strip()
            
        current_section.append(line)
        
        # Also look for command tables or lists
        if ('scpi' in line_lower or 
            'command' in line_lower or 
            line_lower.startswith('*') or
            line_lower.startswith('curr') or
            line_lower.startswith('volt') or
            line_lower.startswith('func') or
            line_lower.startswith('batt')):
            
            # Include surrounding context
            start = max(0, i-5)
            end = min(len(lines), i+10)
            context = lines[start:end]
            
            sections.append({
                'title': f'Command Context (Line {i+1})',
                'content': '\n'.join(context)
            })
    
    # Add final section
    if current_section:
        section_text = '\n'.join(current_section)
        if any(keyword in section_text.lower() for keyword in battery_keywords):
            sections.append({
                'title': section_title,
                'content': section_text
            })
    
    return sections

def extract_commands(text):
    """Extract SCPI commands from the text"""
    if not text:
        return []
        
    commands = []
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Look for SCPI command patterns
        scpi_patterns = [
            r'^\*[A-Z]+\??',  # *IDN?, *RST, etc.
            r'^[A-Z]+:[A-Z]+(\?|$)',  # VOLT:PROT?, CURR:LEV, etc.
            r'^[A-Z]+\??$',  # FUNC?, LOAD, etc.
            r'^[A-Z]+\s+[A-Z]+',  # FUNC BATT, LOAD ON, etc.
        ]
        
        for pattern in scpi_patterns:
            if re.match(pattern, line):
                commands.append(line)
                break
                
        # Also look for command descriptions
        if ('command' in line.lower() and 
            (':' in line or '?' in line or line.isupper())):
            commands.append(line)
    
    return list(set(commands))  # Remove duplicates

def main():
    print("DL3000 PDF Text Extraction")
    print("=" * 30)
    
    # Find PDF files
    pdf_files = []
    for file in os.listdir('.'):
        if file.endswith('.pdf') and 'DL3000' in file:
            pdf_files.append(file)
    
    if not pdf_files:
        print("No DL3000 PDF files found!")
        return
    
    print(f"Found PDF files: {pdf_files}")
    
    all_sections = []
    all_commands = []
    
    for pdf_file in pdf_files:
        print(f"\nProcessing {pdf_file}...")
        
        # Try pdfplumber first
        text = extract_text_with_pdfplumber(pdf_file)
        
        # Fallback to PyPDF2 if pdfplumber fails
        if not text:
            print("pdfplumber failed, trying PyPDF2...")
            text = extract_text_with_pypdf2(pdf_file)
        
        if not text:
            print(f"Failed to extract text from {pdf_file}")
            continue
        
        # Save full text
        output_file = f"{pdf_file}_extracted.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Full text saved to {output_file}")
        
        # Find battery-related sections
        sections = find_battery_related_content(text)
        all_sections.extend(sections)
        
        # Extract commands
        commands = extract_commands(text)
        all_commands.extend(commands)
        
        print(f"Found {len(sections)} battery-related sections")
        print(f"Found {len(commands)} potential commands")
    
    # Save battery-related content
    if all_sections:
        with open('battery_sections.txt', 'w', encoding='utf-8') as f:
            f.write("BATTERY-RELATED SECTIONS FROM DL3000 MANUALS\n")
            f.write("=" * 50 + "\n\n")
            
            for section in all_sections:
                f.write(f"SECTION: {section['title']}\n")
                f.write("-" * len(section['title']) + "\n")
                f.write(section['content'])
                f.write("\n\n" + "="*50 + "\n\n")
        
        print(f"\nBattery-related content saved to battery_sections.txt")
    
    # Save commands
    if all_commands:
        with open('extracted_commands.txt', 'w', encoding='utf-8') as f:
            f.write("SCPI COMMANDS FOUND IN DL3000 MANUALS\n")
            f.write("=" * 40 + "\n\n")
            
            for cmd in sorted(set(all_commands)):
                f.write(f"{cmd}\n")
        
        print(f"Commands saved to extracted_commands.txt")
    
    # Print summary
    print(f"\nSUMMARY:")
    print(f"- Processed {len(pdf_files)} PDF files")
    print(f"- Found {len(all_sections)} battery-related sections")
    print(f"- Found {len(set(all_commands))} unique commands")
    
    # Show some key commands we found
    key_commands = [cmd for cmd in all_commands if 
                   'batt' in cmd.lower() or 
                   'func' in cmd.lower() or 
                   'curr' in cmd.lower() or
                   'volt' in cmd.lower()]
    
    if key_commands:
        print(f"\nKey commands found:")
        for cmd in sorted(set(key_commands))[:10]:  # Show first 10
            print(f"  {cmd}")
    
    print(f"\nNext steps:")
    print(f"1. Review battery_sections.txt for battery mode setup")
    print(f"2. Check extracted_commands.txt for all available commands")
    print(f"3. Use this information to update the DC Load Controller")

if __name__ == "__main__":
    main()
