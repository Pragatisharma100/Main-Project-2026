# Stock VCP Scanner - Main Project 2026

**Made by Pragati**

## Project Overview

Stock VCP Scanner is a **Flask-based web application** designed to analyze Indian stock market data and identify **Validating Volume Candlestick Pattern (VCP)** trading opportunities. It combines a Python backend with a responsive HTML/JavaScript frontend to provide real-time stock scanning, pattern analysis, and custom scanner creation.

### Key Features
- 📊 **Real-time Stock Data Fetching** - Uses yfinance to fetch NSE stock data
- 🔍 **VCP Pattern Detection** - Identifies validating volume candlestick patterns
- 💾 **Data Caching** - Caches stock data for 6 hours to optimize performance
- 🎨 **Interactive Web Interface** - HTML-based frontend with live scanning
- ⚙️ **Custom Scanner Builder** - Create custom scanners with personalized parameters
- 📈 **Multi-Stock Support** - Supports major Indian stocks (AXISBANK, HDFCBANK, ICICIBANK, INFY, LT, RELIANCE, SBIN, TCS)
- 📁 **Result Tracking** - Saves scan results as JSON files for analysis

## Project Structure

```
Main-Project-2026/
├── vcp_scanner.py          # Main Flask backend application
├── index.html              # Home/main dashboard page
├── my-scanners.html        # View and manage saved scanners
├── scanner-builder.html    # Create custom scanners
├── scanner.html            # Individual scanner view
├── requirements.txt        # Python dependencies
├── data/                   # Cached stock OHLCV data (JSON)
└── results/                # Scan results (JSON)
```

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Backend | Flask | 3.0.3 |
| CORS Support | flask-cors | 4.0.1 |
| Stock Data | yfinance | 0.2.40 |
| Data Processing | pandas | 2.2.2 |
| Numerical Computing | numpy | 1.26.4 |
| HTTP Requests | requests | 2.32.3 |

## Installation & Setup

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Step 1: Clone/Open the Project
```bash
cd folder location
```

### Step 2: Create and Activate Virtual Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows)
.venv\Scripts\Activate.ps1

# On macOS/Linux:
# source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

## Running the Project

### Start the Backend Server
```bash
python vcp_scanner.py
```

The Flask server will start on **http://localhost:5000**

**Output:**
```
 * Running on http://127.0.0.1:5000
 Press CTRL+C to quit
```

### Access the Web Interface
Open your browser and navigate to:
- **Home Dashboard**: http://localhost:5000
- **My Scanners**: http://localhost:5000/my-scanners.html
- **Scanner Builder**: http://localhost:5000/scanner-builder.html

## How to Use the Project

### 1. **Running a Stock Scan**
- Go to the Home Dashboard (`index.html`)
- Select stocks to scan from the available list
- Click "Start Scan" to begin analyzing patterns
- View results in real-time as the scan progresses

### 2. **Creating a Custom Scanner**
- Navigate to Scanner Builder (`scanner-builder.html`)
- Define custom parameters for pattern detection
- Save the scanner configuration
- Name and store your custom scanner

### 3. **Managing Your Scanners**
- View all saved scanners in "My Scanners" section
- Edit, delete, or run existing scanners
- Export scan results for further analysis

### 4. **Monitoring Scan Progress**
- Real-time progress bar shows scan completion status
- Logs display which stocks are being analyzed
- Results are saved automatically as JSON files

## Testing the Project

### Quick Test - Check Backend Running
```bash
# In terminal (while server is running)
curl http://localhost:5000/api/status
```

### Test Data Fetching
The project includes sample cached data in the `data/` folder:
```
data/AXISBANK_2023-02-27.json
data/INFY_2026-03-27.json
data/RELIANCE_2022-02-27.json
... (and more)
```

### View Scan Results
Results are automatically saved to the `results/` folder:
```
results/default_2023-02-27.json
results/scanner_1774712610262_2026-03-27.json
... (scan results with timestamps)
```

## API Endpoints (Backend)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Check server status |
| `/api/scan` | POST | Start a new scan |
| `/api/scan-status` | GET | Get scan progress |
| `/api/save-scanner` | POST | Save custom scanner |
| `/api/load-scanners` | GET | Load saved scanners |
| `/api/stocks` | GET | Get available stocks |

## Future Enhancements

- [ ] Database integration for persistent storage
- [ ] Advanced pattern recognition algorithms
- [ ] Historical backtest analysis
- [ ] Email alerts for pattern matches
- [ ] Mobile app support
- [ ] Portfolio tracking

## License

This project is created for educational and research purposes.

## Support

For issues or questions, refer to the code comments and logs in the terminal output.