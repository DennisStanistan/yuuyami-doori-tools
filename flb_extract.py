import os
import struct
import argparse
import hashlib

def get_magic_extension(data):
    if len(data) < 4:
        return 'bin'
        
    magic = struct.unpack('<I', data[:4])[0]
    
    # Check string-based magics
    if data[:3] == b'FLB':
        return 'flb'
        
    if magic == 0x10:
        return 'tim'
    
    magics = {
        0x604c4553: 'sel',  # SEL`
        0x56414270: 'pbav', # pBAV
        0x00444341: 'acd',  # ACD\0
        0x00445645: 'evd',  # EVD\0
        0x0044534c: 'lsd',  # LSD\0
        0x00445651: 'qvd',  # QVD\0
        0x90534145: 'eas',  # EAS\x90
        0x00444650: 'pfd',  # PFD\0
    }
    
    return magics.get(magic, 'bin')

def parse_flb(f, base, output_dir, path_prefix=""):
    f.seek(base)
    magic = f.read(4)
    if magic[:3] != b'FLB':
        print(f"[{path_prefix}] Not an FLB at offset 0x{base:x}")
        return
        
    version = f.read(4)
    header = f.read(24)
    if len(header) < 24:
        return
        
    header_size, idx_start, data_start, count1, count2, total_size = struct.unpack('<6I', header)
    
    print(f"[{path_prefix}] FLB at 0x{base:x}, {count1} main entries, {count2} sub entries")
    
    # Read index entries
    f.seek(base + header_size)
    num_idx = (idx_start - header_size) // 8
    idx_entries = []
    for i in range(num_idx):
        off, hash_val = struct.unpack('<II', f.read(8))
        idx_entries.append((off, hash_val))
        
    # Read data entries if they exist
    data_entries = []
    if data_start > idx_start:
        f.seek(base + idx_start)
        num_data = (data_start - idx_start) // 16
        for i in range(num_data):
            off, cnt, sub, sz = struct.unpack('<IIII', f.read(16))
            data_entries.append((off, cnt, sub, sz))
            
    os.makedirs(output_dir, exist_ok=True)
            
    # Process children
    if data_entries:
        # This FLB has nested groups
        for i, entry in enumerate(data_entries):
            offset, count, sub_count, size = entry
            if size == 0:
                continue
                
            group_base = base + data_start + offset
            group_prefix = f"{path_prefix}G{i:02d}"
            group_dir = os.path.join(output_dir, f"group_{i:02d}")
            
            # Recursively parse group (which is usually an FLB itself)
            parse_flb(f, group_base, group_dir, group_prefix)
    else:
        # This FLB has direct leaf nodes
        leaf_base = base + data_start
        for i, entry in enumerate(idx_entries):
            offset, hash_val = entry
            abs_offset = leaf_base + offset
            
            # Determine size by looking at next offset
            if i + 1 < len(idx_entries):
                size = idx_entries[i+1][0] - offset
            else:
                # For the last entry, we estimate size to end of block
                size = total_size - offset
                
            if size <= 0:
                continue
                
            f.seek(abs_offset)
            # Read first few bytes to determine type
            peek = f.read(min(16, size))
            ext = get_magic_extension(peek)
            
            # If it's a nested FLB, recurse
            if ext == 'flb':
                sub_dir = os.path.join(output_dir, f"sub_{i:04d}_{hash_val:08x}")
                parse_flb(f, abs_offset, sub_dir, f"{path_prefix}L{i:04d}")
            else:
                # It's a leaf file, extract it
                filename = f"file_{i:04d}_{hash_val:08x}.{ext}"
                filepath = os.path.join(output_dir, filename)
                
                # Check if it's mostly empty (can happen with placeholder entries)
                if size > 4 and peek[:4] == b'\x00\x00\x00\x00':
                    # Only write if it has non-zero data
                    f.seek(abs_offset)
                    full_data = f.read(size)
                    if not any(full_data):
                        continue
                    # Write anyway if there is data
                    with open(filepath, 'wb') as out_f:
                        out_f.write(full_data)
                else:
                    # Normal extraction
                    f.seek(abs_offset)
                    with open(filepath, 'wb') as out_f:
                        # Chunked read/write for memory safety on large files
                        remaining = size
                        while remaining > 0:
                            chunk = f.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            out_f.write(chunk)
                            remaining -= len(chunk)

def extract_archive(archive_path, output_dir):
    print(f"Extracting {archive_path} to {output_dir}")
    with open(archive_path, 'rb') as f:
        parse_flb(f, 0, output_dir, "ROOT")
    print("Extraction complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract Yuuyami Doori Tankentai FLB archives")
    parser.add_argument("archive", help="Path to FILELINK.FLB")
    parser.add_argument("output", help="Output directory")
    args = parser.parse_args()
    
    extract_archive(args.archive, args.output)
