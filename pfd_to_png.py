import os
import struct
import argparse
from PIL import Image

def decode_rgb555(color):
    r = (color & 0x1F) * 255 // 31
    g = ((color >> 5) & 0x1F) * 255 // 31
    b = ((color >> 10) & 0x1F) * 255 // 31
    # PFD backgrounds are fully opaque in-game, so alpha is always 255
    a = 255
    return (r, g, b, a)


def extract_pfd(filepath, output_dir):
    filename = os.path.basename(filepath)
    print(f"Processing PFD: {filename}")
    
    with open(filepath, 'rb') as f:
        magic = f.read(4)
        if magic != b'PFD\x00':
            print(f"  Not a valid PFD file")
            return
            
        version = f.read(4)
        total_size = struct.unpack('<I', f.read(4))[0]
        header_end = struct.unpack('<I', f.read(4))[0]
        clut_offset = struct.unpack('<I', f.read(4))[0]
        clut_size = struct.unpack('<I', f.read(4))[0]
        pixel_offset = struct.unpack('<I', f.read(4))[0]
        pixel_size = struct.unpack('<I', f.read(4))[0]
        
        tile_w, tile_h = struct.unpack('<HH', f.read(4))
        tiles_x, tiles_y = struct.unpack('<HH', f.read(4))
        num_sections = struct.unpack('<H', f.read(2))[0]
        
        print(f"  Grid: {tiles_x}x{tiles_y} tiles ({tiles_x * tile_w}x{tiles_y * tile_h} pixels)")
        print(f"  Sections: {num_sections}")
        
        # Read section table starting at 0x2C
        f.seek(0x2C)
        sections = []
        for i in range(num_sections):
            c_off, p_off, sec_w, sec_h = struct.unpack('<IIHH', f.read(12))
            sections.append({
                'clut_offset': c_off,
                'pixel_offset': p_off,
                'w': sec_w,
                'h': sec_h
            })
            
        # Create output image
        img = Image.new('RGBA', (tiles_x * tile_w, tiles_y * tile_h))
        pixels = img.load()
        
        current_x = 0
        for s_idx, sec in enumerate(sections):
            print(f"  Section {s_idx}: {sec['w']}x{sec['h']} tiles, c_off=0x{sec['clut_offset']:x}, p_off=0x{sec['pixel_offset']:x}")
            
            f.seek(clut_offset + sec['clut_offset'])
            clut_data = f.read(sec['w'] * sec['h'] * 32) # 16 colors * 2 bytes = 32 bytes per tile
            
            f.seek(pixel_offset + sec['pixel_offset'])
            pixel_data = f.read(sec['w'] * sec['h'] * (tile_w * tile_h // 2)) # 4bpp = 128 bytes per tile
            
            # Pre-decode all palettes for this section
            palettes = []
            for tile_idx in range(sec['w'] * sec['h']):
                pal_offset = tile_idx * 32
                pal = [decode_rgb555(struct.unpack('<H', clut_data[pal_offset + c*2 : pal_offset + c*2 + 2])[0]) for c in range(16)]
                palettes.append(pal)
                
            # Render as a single linear image
            # Width is sec['w'] * tile_w pixels
            sec_px_w = sec['w'] * tile_w
            sec_px_h = sec['h'] * tile_h
            row_bytes = sec_px_w // 2
            
            idx = 0
            for y in range(sec_px_h):
                for bx in range(row_bytes):
                    b = pixel_data[idx]
                    idx += 1
                    
                    x = bx * 2
                    
                    # Determine which tile this pixel belongs to
                    tile_x = x // tile_w
                    tile_y = y // tile_h
                    tile_idx = tile_y * sec['w'] + tile_x
                    
                    try:
                        pixels[current_x + x, y] = palettes[tile_idx][b & 0x0F]
                        pixels[current_x + x + 1, y] = palettes[tile_idx][(b >> 4) & 0x0F]
                    except Exception:
                        pass # Out of bounds
                    
            current_x += sec_px_w
            
        os.makedirs(output_dir, exist_ok=True)
        out_name = os.path.splitext(filename)[0] + ".png"
        out_path = os.path.join(output_dir, out_name)
        img.save(out_path)
        print(f"  Saved to {out_path}")

def process_directory(input_dir, output_dir):
    # Find all PFD files
    pfd_files = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            if f.endswith('.pfd'):
                pfd_files.append(os.path.join(root, f))
                
    print(f"Found {len(pfd_files)} PFD files")
    for f in pfd_files:
        extract_pfd(f, output_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert PFD panoramas to PNG")
    parser.add_argument("input", help="Input directory containing PFD files")
    parser.add_argument("output", help="Output directory for PNGs")
    args = parser.parse_args()
    
    process_directory(args.input, args.output)
