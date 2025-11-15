# New Zealand Sea Surface Temperature Maps

Automated ocean data visualization for New Zealand waters using Copernicus Marine Service WMTS.

## Automated Updates

GitHub Actions generates maps every 6 hours:
- `latest/temperature.png` - Current sea surface temperature
- `latest/temperature_tomorrow.png` - Tomorrow's forecast
- `latest/anomaly.png` - Current temperature anomaly

Archives are saved to `archive/YYYY-MM-DD/{type}-HHMM.png` for historical reference.

## Usage

```bash
# Current temperature
uv run nz_ocean_map.py

# Temperature anomaly
uv run nz_ocean_map.py --type anomaly

# Tomorrow's forecast
uv run nz_ocean_map.py --type temperature --days 1
```

## Options

```
-t, --type {temperature,anomaly,salinity,currents}  Data type (default: temperature)
-z, --zoom {5,6,7}                                  Zoom level (default: 6)
-d, --days DAYS                                     Days offset (default: 0)
-o, --output FILE                                   Output filename
--no-legend                                         Exclude color scale
--no-title                                          Exclude title banner
```

## Data Source

Copernicus Marine Service GLOBAL_ANALYSISFORECAST_PHY_001_024
- Updates every 6 hours
- Spatial resolution: ~8km (0.083°)

## Requirements

Python 3.12+ with UV package manager

```bash
uv sync
uv run nz_ocean_map.py
```

## License

Creative Commons Attribution License (CC BY 4.0)
