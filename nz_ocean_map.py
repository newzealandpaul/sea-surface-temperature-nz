#!/usr/bin/env python3
"""
Advanced WMTS tile downloader for New Zealand ocean data visualization
Supports multiple data types: temperature, anomaly, salinity, currents
"""

import urllib.request
import urllib.error
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
import os
import argparse

# Preset layers
LAYERS = {
    'temperature': {
        'layer': 'GLOBAL_ANALYSISFORECAST_PHY_001_024/cmems_mod_glo_phy-thetao_anfc_0.083deg_PT6H-i_202406/thetao',
        'style': 'cmap:thermal',
        'elevation': '-0.49402499198913574',
        'name': 'Sea Surface Temperature'
    },
    'anomaly': {
        'layer': 'GLOBAL_ANALYSISFORECAST_PHY_001_024/cmems_mod_glo_phy_anfc_0.083deg-sst-anomaly_P1D-m_202411/sea_surface_temperature_anomaly',
        'style': 'cmap:balance',
        'elevation': None,
        'name': 'Sea Surface Temperature Anomaly'
    },
    'salinity': {
        'layer': 'GLOBAL_ANALYSISFORECAST_PHY_001_024/cmems_mod_glo_phy-so_anfc_0.083deg_PT6H-i_202406/so',
        'style': 'cmap:haline',
        'elevation': '-0.49402499198913574',
        'name': 'Sea Surface Salinity'
    },
    'currents': {
        'layer': 'GLOBAL_ANALYSISFORECAST_PHY_001_024/cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i_202406/sea_water_velocity',
        'style': 'vectorStyle:solidAndVector,cmap:thermal',
        'elevation': '-0.49402499198913574',
        'name': 'Sea Surface Currents'
    }
}

# NZ coverage at different zoom levels
NZ_COVERAGE = {
    5: {'row_start': 22, 'row_end': 24, 'col_start': 61, 'col_end': 64},  # ~640x768px
    6: {'row_start': 44, 'row_end': 48, 'col_start': 123, 'col_end': 127},  # ~1280x1280px
    7: {'row_start': 88, 'row_end': 96, 'col_start': 246, 'col_end': 254},  # ~2304x2304px
}

def get_time_param(days_offset=0, hour_offset=0):
    """
    Get time parameter rounded to nearest 6-hour interval
    Uses Pacific/Auckland timezone for input, converts to UTC for API
    
    Args:
        days_offset: Days from now (0=today, 1=tomorrow, -1=yesterday)
        hour_offset: Additional hours offset
    
    Returns:
        Tuple of (UTC time string in ISO format, NZ time datetime object)
    """
    # Get current time in NZ timezone
    nz_tz = ZoneInfo('Pacific/Auckland')
    now_nz = datetime.now(nz_tz)
    target_nz = now_nz + timedelta(days=days_offset, hours=hour_offset)
    
    # Convert to UTC for the API
    target_utc = target_nz.astimezone(ZoneInfo('UTC'))
    rounded_hour = (target_utc.hour // 6) * 6
    time_rounded_utc = target_utc.replace(hour=rounded_hour, minute=0, second=0, microsecond=0)
    
    # Also get the NZ time for display
    time_rounded_nz = time_rounded_utc.astimezone(nz_tz)
    
    return time_rounded_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z'), time_rounded_nz

def download_tile(layer, tilematrix, tilerow, tilecol, time_param, elevation=None, style="cmap:thermal"):
    """Download a single WMTS tile"""
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
    )
    
    if elevation:
        url += f"&ELEVATION={elevation}"
    
    try:
        print(f"  Tile [{tilerow},{tilecol}]...", end=" ", flush=True)
        with urllib.request.urlopen(url, timeout=30) as response:
            img_data = response.read()
            img = Image.open(BytesIO(img_data))
            print("✓")
            return img
    except Exception as e:
        print(f"✗ {e}")
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

def create_legend_image(colors, labels, target_height, bar_width=60, data_type='temperature'):
    """
    Create a professional-looking legend at the target height

    Args:
        colors: List of (offset, (r, g, b)) tuples
        labels: List of (y_position, text) tuples
        target_height: Desired height of the legend
        bar_width: Width of the color bar
        data_type: Type of data for title/unit selection

    Returns:
        PIL Image object
    """
    from PIL import ImageDraw, ImageFont
    import re

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
        font_large = ImageFont.truetype("PressStart2P.ttf", 24)
        font_title = ImageFont.truetype("PressStart2P.ttf", 18)
    except:
        font_large = ImageFont.load_default()
        font_title = ImageFont.load_default()

    # Draw title based on data type
    title_map = {
        'temperature': ('Temperature', '(degrees C)'),
        'anomaly': ('Anomaly', '(degrees C)'),
        'salinity': ('Salinity', '(PSU)'),
        'currents': ('Velocity', '(m/s)')
    }
    title, unit = title_map.get(data_type, ('Value', ''))

    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (total_width - title_width) // 2
    draw.text((title_x, padding // 2), title, fill='black', font=font_title)

    # Draw unit label
    if unit:
        unit_bbox = draw.textbbox((0, 0), unit, font=font_title)
        unit_width = unit_bbox[2] - unit_bbox[0]
        unit_x = (total_width - unit_width) // 2
        draw.text((unit_x, padding // 2 + 25), unit, fill='black', font=font_title)

    # Extract numeric values from labels
    values = []
    for _, label_text in labels:
        # Try to extract numeric value
        match = re.search(r'([-\d.]+)', label_text)
        if match:
            values.append(float(match.group(1)))

    if values:
        min_val = min(values)
        max_val = max(values)

        # Draw value labels at key positions
        label_x = bar_x + bar_width + padding

        # Determine appropriate format based on data type
        if data_type == 'temperature':
            fmt = "{:.1f}°C"
        elif data_type == 'anomaly':
            fmt = "{:.1f}°C"
        elif data_type == 'salinity':
            fmt = "{:.1f}"
        elif data_type == 'currents':
            fmt = "{:.2f}"
        else:
            fmt = "{:.1f}"

        # Top (max value)
        draw.text((label_x, bar_y_start - 10), fmt.format(max_val), fill='black', font=font_large)

        # Middle
        mid_val = (max_val + min_val) / 2
        mid_y = (bar_y_start + bar_y_end) // 2
        draw.text((label_x, mid_y - 15), fmt.format(mid_val), fill='black', font=font_large)

        # Bottom (min value)
        draw.text((label_x, bar_y_end - 20), fmt.format(min_val), fill='black', font=font_large)

    return img

def parse_svg_legend(svg_data, target_height=None, data_type='temperature'):
    """
    Parse SVG legend and extract colors and labels from gradient stops

    Args:
        svg_data: SVG XML data as bytes
        target_height: Target height for the legend (default: original SVG height)
        data_type: Type of data for legend customization

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
            img = create_legend_image(colors, labels, target_height, data_type=data_type)
        else:
            img = create_legend_image(colors, labels, height, data_type=data_type)

        return img
    except Exception as e:
        print(f"SVG parse error: {e}")
        import traceback
        traceback.print_exc()
        return None

def download_legend(layer, style="cmap:thermal", tiles_grid=None, target_height=None, data_type='temperature'):
    """
    Download the color scale legend from WMTS service as SVG and convert to image

    Args:
        layer: Layer identifier
        style: Style parameter
        tiles_grid: Not used, kept for compatibility
        target_height: Desired height for the legend
        data_type: Type of data for legend customization

    Returns:
        PIL Image object or None
    """
    import urllib.parse

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
            img = parse_svg_legend(svg_data, target_height=target_height, data_type=data_type)
            if img:
                print(f"✓ ({img.width}x{img.height}px)")
                return img
            return None
    except Exception as e:
        print(f"✗ {e}")
        return None

def stitch_tiles(tiles_grid, tile_size=256):
    """Stitch a grid of tiles into a single image"""
    rows = len(tiles_grid)
    cols = len(tiles_grid[0]) if rows > 0 else 0
    
    width = cols * tile_size
    height = rows * tile_size
    output = Image.new('RGB', (width, height))
    
    for row_idx, row in enumerate(tiles_grid):
        for col_idx, tile in enumerate(row):
            if tile is not None:
                x = col_idx * tile_size
                y = row_idx * tile_size
                output.paste(tile, (x, y))
    
    return output

def add_title(image, title, time_str):
    """Add a title banner to the image"""
    # Create new image with space for title
    title_height = 60
    new_image = Image.new('RGB', (image.width, image.height + title_height), color='white')
    
    # Paste original image below title
    new_image.paste(image, (0, title_height))
    
    # Draw title
    draw = ImageDraw.Draw(new_image)
    try:
        font = ImageFont.truetype("PressStart2P.ttf", 24)
        font_small = ImageFont.truetype("PressStart2P.ttf", 14)
    except:
        font = ImageFont.load_default()
        font_small = font
    
    # Draw title text
    draw.text((10, 10), title, fill='black', font=font)
    draw.text((10, 38), f"Time: {time_str}", fill='gray', font=font_small)
    
    return new_image

def create_map(data_type='temperature', output_file=None, zoom_level=6, days_offset=0, with_legend=True, with_title=True):
    """
    Create a map of New Zealand ocean data

    Args:
        data_type: Type of data ('temperature', 'anomaly', 'salinity', 'currents')
        output_file: Output filename (auto-generated if None)
        zoom_level: WMTS zoom level (5, 6, or 7)
        days_offset: Days offset (0=today, 1=tomorrow, -1=yesterday)
        with_legend: Include legend in output
        with_title: Include title banner in output
    """
    if data_type not in LAYERS:
        print(f"✗ Unknown data type: {data_type}")
        print(f"  Available: {', '.join(LAYERS.keys())}")
        return False
    
    if zoom_level not in NZ_COVERAGE:
        print(f"✗ Unsupported zoom level: {zoom_level}")
        print(f"  Available: {', '.join(map(str, NZ_COVERAGE.keys()))}")
        return False
    
    config = LAYERS[data_type]
    coverage = NZ_COVERAGE[zoom_level]
    
    # Generate output filename if not provided
    if output_file is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"nz_{data_type}_z{zoom_level}_{timestamp}.png"
    
    print("=" * 80)
    print(f"New Zealand {config['name']} Map")
    print("=" * 80)
    
    # Get time parameter (returns UTC for API and NZ time for display)
    time_param, time_nz = get_time_param(days_offset)
    time_display = time_nz.strftime('%Y-%m-%d %H:%M NZDT' if time_nz.dst() else '%Y-%m-%d %H:%M NZST')
    
    rows = coverage['row_end'] - coverage['row_start'] + 1
    cols = coverage['col_end'] - coverage['col_start'] + 1
    total_tiles = rows * cols
    
    print(f"\nConfiguration:")
    print(f"  Data type: {data_type}")
    print(f"  Time: {time_display}")
    print(f"  Zoom level: {zoom_level}")
    print(f"  Tile range: rows {coverage['row_start']}-{coverage['row_end']}, cols {coverage['col_start']}-{coverage['col_end']}")
    print(f"  Total tiles: {total_tiles}")
    print()
    
    # Download tiles
    print("Downloading tiles:")
    tiles_grid = []
    for row in range(coverage['row_start'], coverage['row_end'] + 1):
        tile_row = []
        for col in range(coverage['col_start'], coverage['col_end'] + 1):
            tile = download_tile(
                layer=config['layer'],
                tilematrix=zoom_level,
                tilerow=row,
                tilecol=col,
                time_param=time_param,
                elevation=config['elevation'],
                style=config['style']
            )
            tile_row.append(tile)
        tiles_grid.append(tile_row)
    
    # Check success
    successful_tiles = sum(1 for row in tiles_grid for tile in row if tile is not None)
    if successful_tiles == 0:
        print("\n✗ Failed to download any tiles!")
        return False
    
    print(f"\n✓ Downloaded {successful_tiles}/{total_tiles} tiles")
    
    # Stitch tiles
    print("\nStitching tiles...")
    final_image = stitch_tiles(tiles_grid)

    # Add title
    if with_title:
        print("Adding title...")
        final_image = add_title(final_image, config['name'], time_display)

    # Add legend
    if with_legend:
        print("\nAdding color scale...")
        legend = download_legend(config['layer'], config['style'], tiles_grid=tiles_grid,
                                target_height=final_image.height, data_type=data_type)
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
    
    # Save
    print(f"\nSaving to {output_file}...")
    final_image.save(output_file, optimize=True)
    
    file_size = os.path.getsize(output_file) / (1024 * 1024)
    
    print(f"\n✓ Success!")
    print(f"  Output: {output_file}")
    print(f"  Size: {final_image.width}x{final_image.height} pixels")
    print(f"  File size: {file_size:.2f} MB")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Download and stitch WMTS tiles for New Zealand ocean data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Current temperature at default zoom
  %(prog)s
  
  # Tomorrow's temperature forecast
  %(prog)s --type temperature --days 1
  
  # Today's temperature anomaly
  %(prog)s --type anomaly
  
  # High resolution salinity map
  %(prog)s --type salinity --zoom 7
  
  # Yesterday's currents without color scale
  %(prog)s --type currents --days -1 --no-legend

Available data types:
  temperature - Sea surface temperature (°C) with thermal color scale
  anomaly     - Temperature anomaly from 1993-2016 climatology (°C) with balance color scale
  salinity    - Sea surface salinity (PSU) with haline color scale
  currents    - Sea surface currents (m/s) with velocity color scale

Color scales are automatically extracted from WMTS and embedded in the output image.
        """
    )
    
    parser.add_argument('-t', '--type', default='temperature', choices=LAYERS.keys(),
                        help='Type of data to visualize (default: temperature)')
    parser.add_argument('-z', '--zoom', type=int, default=6, choices=NZ_COVERAGE.keys(),
                        help='Zoom level: 5=low, 6=medium, 7=high (default: 6)')
    parser.add_argument('-d', '--days', type=int, default=0,
                        help='Days offset: 0=today, 1=tomorrow, -1=yesterday (default: 0)')
    parser.add_argument('-o', '--output',
                        help='Output filename (auto-generated if not specified)')
    parser.add_argument('--no-legend', action='store_true',
                        help='Exclude color scale from output (included by default)')
    parser.add_argument('--no-title', action='store_true',
                        help='Exclude title banner from output (included by default)')

    args = parser.parse_args()

    try:
        success = create_map(
            data_type=args.type,
            output_file=args.output,
            zoom_level=args.zoom,
            days_offset=args.days,
            with_legend=not args.no_legend,
            with_title=not args.no_title
        )
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
