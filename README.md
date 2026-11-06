# WattWise — Electricity Consumption Analysis System

> **College Capstone Project | Final Production Release**  
> Built with **Python 3.12**, **Flask**, **MySQL 8.0** (with transparent SQLite local fallback), **Pandas**, **Chart.js**, and **ReportLab**.

---

## ⚡ Overview

**WattWise** is a commercial-grade electricity consumption intelligence platform. It tracks time-series cumulative meter readings, validates chronological monotonic progression, automatically computes period consumption, models progressive tiered electricity tariffs, estimates carbon footprint emissions, surfaces high-usage anomalies, and exports executive reports in CSV, PDF, and printable formats.

---

## 🏛️ System Architecture

```
                          ┌──────────────────────────────────────┐
                          │     Modern Responsive Web UI        │
                          │   (HTML5, CSS3, JS, Chart.js 4)      │
                          └──────────────────┬───────────────────┘
                                             │ HTTP Requests
                                             ▼
                          ┌──────────────────────────────────────┐
                          │          Flask Application           │
                          │              (app.py)                │
                          └───────┬──────────────────────┬───────┘
                                  │                      │
                   ┌──────────────┴──────────┐    ┌──────┴───────────────┐
                   │   Calculation Engine    │    │  Reporting Service   │
                   │(services/calculator.py) │    │(services/reporting.py│
                   │  - Period Usage (kWh)   │    │  - CSV Export Engine │
                   │  - Tiered Slabs & Tax   │    │  - ReportLab PDF     │
                   │  - Carbon Footprint     │    │  - Printable View    │
                   │  - Monotonic Validation │    └──────────────────────┘
                   └──────────────┬──────────┘
                                  │
                                  ▼
                   ┌──────────────────────────────────────┐
                   │       Unified Database Adapter       │
                   │               (db.py)                │
                   └───────┬──────────────────────┬───────┘
                           │                      │
             (Primary)     ▼                      ▼   (Transparent Fallback)
         ┌───────────────────┐                  ┌───────────────────┐
         │     MySQL 8.0     │                  │   SQLite Local    │
         │  (Database Server)│                  │   (wattwise.db)   │
         │- Foreign Keys     │                  │- Auto-configured  │
         │- Stored Triggers  │                  │- Custom Functions │
         │- Indices          │                  │- Zero Dependencies│
         └───────────────────┘                  └───────────────────┘
```

---

## ✨ Features & Capabilities

### 1. Consumer & Facility Directory
- Manage residential households, commercial complexes, industrial mills, and agricultural irrigation cooperatives.
- Store contact phone numbers, email addresses, geographical regions (Tirupati, Chittoor, Nellore, Kadapa, Madanapalle), and active/inactive status.
- Dedicated **Consumer Profile Page (`/consumers/<id>`)** showing linked hardware meters, lifetime consumption, estimated bills, and historical usage charts.

### 2. Meter Hardware Registry
- Register hardware electricity meters with unique serial codes (e.g., `WW-TPT-101`, `WW-NEL-301`).
- Link meters directly to active consumers with rated capacities and installation dates.
- Filter, search, and toggle active status.

### 3. Chronological Meter Reading Collection
- Capture dated cumulative meter readings (kWh) with inspection notes.
- **Strict Monotonic Validation:** Automatically checks that reading values do not decrease compared to prior readings, and do not exceed subsequent readings.
- **Duplicate Prevention:** Rejects duplicate entries on the same date for the same meter.
- **Subsequent Recalculation:** If historical readings are inserted or deleted, all subsequent interval calculations are automatically recalculated.

### 4. Progressive Tiered Tariff & Energy Billing
- Models real-world progressive tariff structures:
  - **Residential:** Tiered slabs (0–100 @ ₹3.30, 101–200 @ ₹4.80, 201–400 @ ₹6.50, >400 @ ₹8.20) + fixed meter fee + 6% electricity duty.
  - **Commercial:** Two-tier progressive tariff + commercial fixed charges.
  - **Industrial:** Uniform commercial load tariff.
  - **Agricultural:** Subsidized farming rates.

### 5. Environmental Carbon Footprint Tracking
- Estimates greenhouse gas emissions in **kg CO₂** using standard Southern Grid emission factors (0.82 kg CO₂/kWh).

### 6. Interactive Visual Analytics
- **Monthly Usage Progression:** Interactive filled-area line and bar charts showing seasonal energy fluctuations (e.g., cooling spikes in April–June).
- **Regional Energy Distribution:** Aggregated consumption across municipalities.
- **Top Consumers Ranking:** Horizontal ranked bar chart of highest energy consumers.
- **Sector Breakdown:** Interactive doughnut chart of consumer sector shares.

### 7. High-Usage Surveillance & Alerts
- Configurable consumption threshold (default: 500 kWh).
- Instant quick-preset buttons (250, 500, 750, 1000, 2000 kWh).
- Categorized severity pills: **Critical** (≥2000 kWh), **High** (≥1000 kWh), **Elevated** (≥500 kWh).

### 8. Multi-Format Reports Center
- **CSV Raw Data Export (`/reports.csv`):** UTF-8 BOM-encoded CSV ready for Excel, Pandas, or Power BI.
- **Executive PDF Report (`/reports.pdf`):** Branded PDF generated via ReportLab containing an executive KPI scorecard and detailed reading ledger.
- **Printable Audit View (`/reports/print`):** Browser-printable page with dedicated `@media print` styling and faculty examiner signature blocks.

### 9. Dual-Engine Database Reliability
- **MySQL 8.0 Primary:** Runs on local MySQL Server using standard schema DDL (`schema.sql`), stored triggers, and indexes.
- **SQLite Transparent Fallback:** If MySQL credentials are not yet configured or server is unreachable, WattWise automatically initializes and operates on `wattwise.db` with identical schemas and custom functions—ensuring zero startup failures!

---

## 🚀 Quick Setup Instructions (Windows & VS Code)

### Prerequisites
- Python 3.10, 3.11, or 3.12 installed ([python.org](https://www.python.org/downloads/))
- VS Code or any text editor

### Step 1: Open Project in VS Code
Open the project folder:
```
C:\Users\admin\OneDrive\Desktop\Python(electricity)
```

### Step 2: Install Dependencies
Open a PowerShell terminal in VS Code and run:
```powershell
pip install -r electricity_consumption_analysis/requirements.txt
```

### Step 3: Populate Demo Data (Optional but Recommended)
Seed the database with 10 realistic consumers, 10 meters, and 140 chronological readings:
```powershell
python seed_demo.py
```

### Step 4: Start the Application
Run the launcher:
```powershell
python run.py
```
Or run directly from the project directory:
```powershell
cd electricity_consumption_analysis
python app.py
```

### Step 5: Open in Your Browser
Open: [**http://127.0.0.1:5000**](http://127.0.0.1:5000)

---

## 🗄️ MySQL 8.0 Configuration Guide

WattWise includes full native MySQL 8.0 support.

### To use your local MySQL 8.0 Server:
1. Verify that your **MySQL80** Windows Service is running (in Task Manager or `services.msc`).
2. Open `electricity_consumption_analysis/.env` in VS Code.
3. Enter your MySQL password:
   ```ini
   MYSQL_HOST=localhost
   MYSQL_PORT=3306
   MYSQL_USER=root
   MYSQL_PASSWORD=your_actual_mysql_password
   MYSQL_DB=electricity_analysis
   DB_ENGINE=mysql
   ```
4. Run the database initialization script:
   ```powershell
   python init_db.py --mysql
   ```
   *This automatically creates the `electricity_analysis` database, runs `schema.sql`, sets up tables, constraints, and stored triggers.*
5. Seed sample data into MySQL:
   ```powershell
   python seed_demo.py
   ```
6. Visit `http://127.0.0.1:5000/system` to verify that **MYSQL 8.0 ENGINE ACTIVE** is displayed.

---

## 🧪 Automated Testing

WattWise includes a comprehensive automated test suite built with `pytest`.

To run all automated tests:
```powershell
pytest electricity_consumption_analysis/tests -v
```

### Test Coverage (24 Passed Tests):
- ✅ `test_period_consumption_baseline` — Verifies first reading creates baseline.
- ✅ `test_period_consumption_normal_progression` — Verifies delta calculation.
- ✅ `test_period_consumption_zero_usage` — Verifies zero load handling.
- ✅ `test_period_consumption_decreasing_raises_value_error` — Rejects decreasing readings.
- ✅ `test_tariff_residential_slabs` — Tests tiered tariff math and taxes.
- ✅ `test_tariff_commercial` — Tests commercial tariff rules.
- ✅ `test_carbon_footprint_calculation` — Validates grid emissions factor.
- ✅ `test_daily_average_calculation` — Validates daily load calculation.
- ✅ `test_consumer_and_meter_foreign_key` — Validates relational integrity.
- ✅ `test_sequential_reading_recalculation` — Validates automatic recalculation.
- ✅ `test_dashboard_page` — Tests executive overview route.
- ✅ `test_consumer_flow` — Tests consumer creation, listing, detail, toggle.
- ✅ `test_meter_registration_and_toggle` — Tests meter registration.
- ✅ `test_readings_submission_and_validation` — Tests reading submission.
- ✅ `test_analytics_and_alerts_routes` — Tests analytics filtering and thresholding.
- ✅ `test_reports_exports` — Tests CSV, PDF, and printable downloads.
- ✅ `test_rest_api_endpoints` — Tests `/api/monthly`, `/api/regions`, `/api/db-status`.
- ✅ `test_system_diagnostics_page` — Tests system health monitoring.
- ✅ `test_404_error_page` — Tests custom 404 handler.
- ✅ `test_valid_reading_input` — Tests input boundary validation.
- ✅ `test_duplicate_date_validation` — Tests duplicate date rejection.
- ✅ `test_decreasing_cumulative_reading` — Rejects lower values.
- ✅ `test_higher_than_future_reading` — Prevents out-of-order anomalies.
- ✅ `test_negative_reading_value` — Rejects negative values.

---

## 🎓 College Viva Demonstration Checklist

When presenting this project to examiners or professors, follow this sequence:

| Step | Page / Action | Key Point to Explain to Examiner |
|------|---------------|----------------------------------|
| **1** | **Dashboard (`/`)** | Point out the 4 KPI cards, month-over-month trend (% change), interactive Chart.js line curve, and high-usage alerts widget. |
| **2** | **Consumers (`/consumers`)** | Demonstrate real-time instant search, sector filtering (Commercial, Industrial, Residential), and click **Profile** on any consumer to show the detailed consumption view. |
| **3** | **Meter Registry (`/meters`)** | Explain hardware-to-consumer foreign key mapping and unique serial number constraint. |
| **4** | **Readings (`/readings`)** | Click **+ Record Reading**. Select a meter to show the dynamic helper (`Previous reading: X kWh. New reading must be ≥ X`). Show that duplicate dates and decreasing values are blocked. |
| **5** | **Analytics (`/analytics`)** | Explain the 4 charts (Monthly Trend, Regional Share, Consumer Ranking, Sector Share) and date range filtering. |
| **6** | **Surveillance (`/alerts`)** | Change the threshold to 750 or 1000 kWh to demonstrate real-time severity classification (**Critical**, **High**, **Elevated**). |
| **7** | **Reports (`/reports`)** | Click **Download PDF Report** to show the ReportLab PDF; click **Open Printable View** to show the print-ready audit document. |
| **8** | **System Diagnostics (`/system`)** | Explain dual-engine architecture (MySQL 8.0 + SQLite fallback) and table record counts. |

### Anticipated Viva Questions & Technical Answers

1. **Q: Why are meter readings stored as cumulative rather than interval usage?**  
   *A:* Real-world utility meters are cumulative odometers that register lifetime consumption. Storing cumulative values ensures that no consumption is lost, meter reads can be independently audited, and interval consumption is derived mathematically: $\text{Consumption} = \text{Reading}_t - \text{Reading}_{t-1}$.

2. **Q: How does WattWise prevent database anomalies?**  
   *A:* Foreign key constraints (`ON DELETE RESTRICT`) prevent deleting consumers with active meters; unique composite keys `(meter_id, reading_date)` prevent duplicate readings; server-side and trigger-level validation prevents non-monotonic entries; and parameterized SQL queries protect against SQL injection.

3. **Q: How is tiered electricity billing calculated?**  
   *A:* The `calculate_tariff()` function in `services/calculator.py` uses progressive slabs where each block of units is charged at its respective rate rather than charging the entire amount at the highest tier.

---

## 👥 Team Handover Guide

- **Lead Controller:** `app.py`
- **Calculation Logic:** `services/calculator.py`
- **Reporting & PDF Engine:** `services/reporting.py`
- **Database Engine:** `db.py`
- **Schema DDL:** `schema.sql`
- **Database Initializer:** `init_db.py`
- **Demo Data Generator:** `seed_demo.py`
- **Automated Tests:** `tests/`
- **Styles & Scripts:** `static/css/style.css`, `static/js/app.js`

---

## 🔒 Security & Reliability

- All SQL interactions use **parameterized queries** (`%s` / `?`).
- Database credentials are loaded from environment variables (`.env`).
- State-changing operations are validated on the server.
- Errors are logged with human-friendly fallback pages.
- Automatic database failover prevents application crash if MySQL server is stopped.
