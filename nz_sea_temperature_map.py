#!/usr/bin/env python3
"""
Download and stitch WMTS tiles to create a New Zealand sea surface temperature map
"""

import urllib.request
import urllib.error
import urllib.parse
from PIL import Image
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
import os

def get_current_time_param():
    """Get current time rounded to nearest 6-hour interval in ISO format (UTC)
    Uses Pacific/Auckland timezone for determining 'now'
    """
    nz_tz = ZoneInfo('Pacific/Auckland')
    now_nz = datetime.now(nz_tz)
    now_utc = now_nz.astimezone(ZoneInfo('UTC'))
    rounded_hour = (now_utc.hour // 6) * 6
    time_rounded = now_utc.replace(hour=rounded_hour, minute=0, second=0, microsecond=0)
    return time_rounded.strftime('%Y-%m-%dT%H:%M:%S.000Z')

def download_tile(layer, tilematrix, tilerow, tilecol, time_param, elevation="-0.49402499198913574", style="cmap:thermal"):
    """
    Download a single WMTS tile
    
    Args:
        layer: Layer identifier (e.g., product/dataset/variable)
        tilematrix: Zoom level
        tilerow: Row index
        tilecol: Column index
        time_param: Time in ISO format
        elevation: Depth in meters (default: surface)
        style: Color map style
    
    Returns:
        PIL Image object or None if failed
    """
    base_url = "https://wmts.marine.copernicus.eu/teroWmts"
    
    url = (
        f"{base_url}?SERVICE=WMTS&REQUEST=GetTile"
        f"&LAYER={layer}"
        f"&STYLE={style}"
        f"&TILEMATRIXSET=EPSG:4326"
        f"&TILEMATRIX={tilematrix}"
        f"&TILEROW={tilerow}"
        f"&TILECOL={tilecol}"
        f"&FORMAT=image/png"
        f"&TIME={time_param}"
        f"&ELEVATION={elevation}"
    )
    
    try:
        print(f"Downloading tile: row={tilerow}, col={tilecol}...", end=" ")
        with urllib.request.urlopen(url, timeout=30) as response:
            img_data = response.read()
            img = Image.open(BytesIO(img_data))
            print("✓")
            return img
    except urllib.error.HTTPError as e:
        print(f"✗ HTTP Error {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def print_legend_to_terminal(color_values, labels):
    """
    Print a visual representation of the legend to the terminal using ANSI colors

    Args:
        color_values: List of RGB tuples
        labels: List of (y_position, label_text) tuples
    """
    if not color_values:
        return

    print("\n  Legend Preview:")
    print("  " + "─" * 40)

    # Display ~20 color bars
    num_bars = min(20, len(color_values))
    step = len(color_values) // num_bars if num_bars > 0 else 1

    for i in range(num_bars):
        idx = min(i * step, len(color_values) - 1)
        r, g, b = color_values[idx]
        # ANSI escape code for RGB color
        color_code = f"\033[48;2;{r};{g};{b}m"
        reset_code = "\033[0m"
        bar = color_code + "    " + reset_code
        print(f"  {bar} rgb({r:3d}, {g:3d}, {b:3d})")

    print("  " + "─" * 40)
    if labels:
        print(f"  Range: {labels[0][1] if labels else 'N/A'} to {labels[-1][1] if labels else 'N/A'}")
    print()

def create_legend_image(colors, labels, target_height, bar_width=60):
    """
    Create a professional-looking legend at the target height

    Args:
        colors: List of (offset, (r, g, b)) tuples
        labels: List of (y_position, text) tuples
        target_height: Desired height of the legend
        bar_width: Width of the color bar

    Returns:
        PIL Image object
    """
    from PIL import ImageDraw, ImageFont

    # Dimensions
    padding = 40
    label_width = 120
    total_width = padding + bar_width + padding + label_width + padding

    # Create image
    img = Image.new('RGB', (total_width, target_height), color='white')
    draw = ImageDraw.Draw(img)

    # Calculate gradient bar position
    bar_x = padding
    bar_y_start = padding * 2
    bar_y_end = target_height - padding * 2
    bar_height = bar_y_end - bar_y_start

    # Draw the gradient bar
    for y in range(bar_height):
        ratio = y / bar_height
        # Find the two colors to interpolate between
        for i in range(len(colors) - 1):
            offset1, color1 = colors[i]
            offset2, color2 = colors[i + 1]
            if offset1 / 100 <= ratio <= offset2 / 100:
                # Interpolate between the two colors
                blend = (ratio - offset1 / 100) / ((offset2 - offset1) / 100) if offset2 != offset1 else 0
                r = int(color1[0] * (1 - blend) + color2[0] * blend)
                g = int(color1[1] * (1 - blend) + color2[1] * blend)
                b = int(color1[2] * (1 - blend) + color2[2] * blend)
                draw.line([(bar_x, bar_y_start + y), (bar_x + bar_width, bar_y_start + y)], fill=(r, g, b))
                break

    # Draw border around gradient bar
    draw.rectangle([bar_x, bar_y_start, bar_x + bar_width, bar_y_end], outline='black', width=2)

    # Load font (larger for better readability)
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        font_title = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        font_large = ImageFont.load_default()
        font_title = ImageFont.load_default()

    # Draw title
    title = "Temperature"
    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (total_width - title_width) // 2
    draw.text((title_x, padding // 2), title, fill='black', font=font_title)

    # Draw unit label
    unit = "(degrees C)"
    unit_bbox = draw.textbbox((0, 0), unit, font=font_title)
    unit_width = unit_bbox[2] - unit_bbox[0]
    unit_x = (total_width - unit_width) // 2
    draw.text((unit_x, padding // 2 + 25), unit, fill='black', font=font_title)

    # Extract temperature values from labels
    temp_values = []
    for _, label_text in labels:
        # Try to extract numeric value
        import re
        match = re.search(r'([\d.]+)', label_text)
        if match:
            temp_values.append(float(match.group(1)))

    if temp_values:
        min_temp = min(temp_values)
        max_temp = max(temp_values)

        # Draw temperature labels at key positions
        label_x = bar_x + bar_width + padding

        # Top (max temperature)
        draw.text((label_x, bar_y_start - 10), f"{max_temp:.1f}°C", fill='black', font=font_large)

        # Middle
        mid_temp = (max_temp + min_temp) / 2
        mid_y = (bar_y_start + bar_y_end) // 2
        draw.text((label_x, mid_y - 15), f"{mid_temp:.1f}°C", fill='black', font=font_large)

        # Bottom (min temperature)
        draw.text((label_x, bar_y_end - 20), f"{min_temp:.1f}°C", fill='black', font=font_large)

    return img

def parse_svg_legend(svg_data, target_height=None):
    """
    Parse SVG legend and extract colors and labels from gradient stops

    Args:
        svg_data: SVG XML data as bytes
        target_height: Target height for the legend (default: original SVG height)

    Returns:
        PIL Image object or None
    """
    import xml.etree.ElementTree as ET
    import re

    try:
        root = ET.fromstring(svg_data)
        ns = {'svg': 'http://www.w3.org/2000/svg'}

        # Extract SVG dimensions
        width = int(root.get('width', 125))
        height = int(root.get('height', 300))

        # Find gradient stops
        stops = root.findall('.//svg:linearGradient/svg:stop', ns)
        if not stops:
            # Fallback: try without namespace
            stops = root.findall('.//stop')

        colors = []
        for stop in stops:
            stop_color = stop.get('stop-color')
            offset = stop.get('offset', '0%').rstrip('%')

            if stop_color and stop_color.startswith('rgb'):
                # Parse rgb(r,g,b) format
                match = re.match(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', stop_color)
                if match:
                    r, g, b = map(int, match.groups())
                    offset_val = float(offset)
                    colors.append((offset_val, (r, g, b)))

        # Sort by offset
        colors.sort(key=lambda x: x[0])
        color_values = [c[1] for c in colors]

        # Extract text labels
        texts = root.findall('.//svg:text', ns)
        if not texts:
            texts = root.findall('.//text')

        labels = []
        for text in texts:
            y = float(text.get('y', 0))
            label_text = ''.join(text.itertext()).strip()
            if label_text:
                labels.append((y, label_text))

        # Sort labels by y position
        labels.sort(key=lambda x: x[0])

        # Print legend to terminal
        print_legend_to_terminal(color_values, labels)

        # Create the legend image at target height
        if target_height:
            img = create_legend_image(colors, labels, target_height)
        else:
            img = create_legend_image(colors, labels, height)

        return img
    except Exception as e:
        print(f"SVG parse error: {e}")
        import traceback
        traceback.print_exc()
        return None

def download_legend(layer, style="cmap:thermal", tiles_grid=None, target_height=None):
    """
    Download the color scale legend from WMTS service as SVG and convert to image

    Args:
        layer: Layer identifier
        style: Style parameter
        tiles_grid: Not used, kept for compatibility
        target_height: Desired height for the legend

    Returns:
        PIL Image object or None
    """
    base_url = "https://wmts.marine.copernicus.eu/teroWmts"

    # Use SVG format (image/svg+xml needs to be URL encoded as image/svg%2Bxml)
    url = (
        f"{base_url}?"
        f"SERVICE=WMTS&"
        f"REQUEST=GetLegend&"
        f"LAYER={urllib.parse.quote(layer, safe='')}&"
        f"STYLE={urllib.parse.quote(style, safe='')}&"
        f"FORMAT=image/svg%2Bxml"
    )

    try:
        print("Downloading color scale...", end=" ", flush=True)
        with urllib.request.urlopen(url, timeout=30) as response:
            svg_data = response.read()

            # Parse SVG manually with target height
            img = parse_svg_legend(svg_data, target_height=target_height)
            if img:
                print(f"✓ ({img.width}x{img.height}px)")
                return img
            return None
    except Exception as e:
        print(f"✗ {e}")
        return None

def stitch_tiles(tiles_grid, tile_size=256):
    """
    Stitch a grid of tiles into a single image
    
    Args:
        tiles_grid: 2D list of PIL Image objects [row][col]
        tile_size: Size of each tile in pixels (default: 256)
    
    Returns:
        PIL Image object
    """
    rows = len(tiles_grid)
    cols = len(tiles_grid[0]) if rows > 0 else 0
    
    # Create output image
    width = cols * tile_size
    height = rows * tile_size
    output = Image.new('RGB', (width, height))
    
    # Paste tiles
    for row_idx, row in enumerate(tiles_grid):
        for col_idx, tile in enumerate(row):
            if tile is not None:
                x = col_idx * tile_size
                y = row_idx * tile_size
                output.paste(tile, (x, y))
    
    return output

def create_nz_temperature_map(output_filename="nz_sea_temperature.png", zoom_level=6):
    """
    Create a map of New Zealand sea surface temperature
    
    Args:
        output_filename: Output file path
        zoom_level: WMTS zoom level (default: 6)
    """
    print("=" * 80)
    print("New Zealand Sea Surface Temperature Map Generator")
    print("=" * 80)
    
    # Configuration for New Zealand coverage
    # At zoom level 6, NZ spans approximately:
    # Latitude: -48° to -33° (rows 44-48)
    # Longitude: 165° to 180° (cols 123-126)
    
    layer = "GLOBAL_ANALYSISFORECAST_PHY_001_024/cmems_mod_glo_phy-thetao_anfc_0.083deg_PT6H-i_202406/thetao"
    
    # Tile ranges for New Zealand
    row_start = 44
    row_end = 48  # inclusive
    col_start = 123
    col_end = 127  # inclusive (extended to include eastern NZ)
    
    # Get current time
    time_param = get_current_time_param()
    print(f"\nFetching data for: {time_param}")
    print(f"Zoom level: {zoom_level}")
    print(f"Tile range: rows {row_start}-{row_end}, cols {col_start}-{col_end}")
    print(f"Total tiles: {(row_end - row_start + 1) * (col_end - col_start + 1)}")
    print()
    
    # Download all tiles
    tiles_grid = []
    for row in range(row_start, row_end + 1):
        tile_row = []
        for col in range(col_start, col_end + 1):
            tile = download_tile(
                layer=layer,
                tilematrix=zoom_level,
                tilerow=row,
                tilecol=col,
                time_param=time_param,
                elevation="-0.49402499198913574",
                style="cmap:thermal"
            )
            tile_row.append(tile)
        tiles_grid.append(tile_row)
    
    # Check if we got any tiles
    total_tiles = sum(1 for row in tiles_grid for tile in row if tile is not None)
    if total_tiles == 0:
        print("\n✗ Failed to download any tiles!")
        return False
    
    print(f"\n✓ Successfully downloaded {total_tiles} tiles")
    
    # Stitch tiles together
    print("\nStitching tiles together...")
    final_image = stitch_tiles(tiles_grid)
    
    # Download and embed color scale
    print("\nAdding color scale...")
    legend = download_legend(layer, style="cmap:thermal", tiles_grid=tiles_grid, target_height=final_image.height)
    if legend:
        # Create new image with legend (legend is already at the correct height)
        padding = 20
        combined = Image.new('RGB',
                           (final_image.width + legend.width + padding, final_image.height),
                           color='white')
        combined.paste(final_image, (0, 0))
        combined.paste(legend, (final_image.width + padding, 0))

        final_image = combined
        print("✓ Color scale embedded")
    else:
        print("⚠ Could not download color scale, continuing without it")
    
    # Save the result
    print(f"Saving to {output_filename}...")
    final_image.save(output_filename)
    
    # Get file size
    file_size = os.path.getsize(output_filename)
    file_size_mb = file_size / (1024 * 1024)
    
    print(f"\n✓ Success!")
    print(f"  Output: {output_filename}")
    print(f"  Size: {final_image.width}x{final_image.height} pixels")
    print(f"  File size: {file_size_mb:.2f} MB")
    print(f"  Time: {time_param}")
    
    return True

def main():
    """Main function"""
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
    else:
        output_file = "nz_sea_temperature.png"
    
    try:
        success = create_nz_temperature_map(output_file)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
