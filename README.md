# M_D Chippa - Inventory & AI Expiry Management System

A Django-based enterprise inventory system enhanced with machine learning for predictive batch expiry risk management.

---

## 🚀 Key Features

- **Authenticated CRUD for Products & Batches**: Complete tracking of product items, manufacturing dates, expiry dates, batch quantities, and storage assignments.
- **Storage Location Monitoring**: Record and update storage parameters (temperature and humidity) for distinct locations.
- **AI Predictive Expiry Engine**: Predicts batch expiry probability using a Random Forest Classifier trained on days-to-expiry, batch quantity, sales velocity, and storage conditions.
- **Four Risk Tiers**: Automatical classification into `Critical` (<7 days), `High` (8-30 days), `Medium` (31-60 days), and `Low` (>60 days).
- **Alert Notifications (Email, SMS & In-App)**: Real-time dispatch of alerts for Critical and High-risk classifications.
- **Alert Escalation & Audit Log**: Tracks the full lifecycle of alerts (Generated, Dispatched, Acknowledged, Resolved) and escalates unacknowledged alerts.
- **Role-Based Access Control (RBAC)**: Support for four user levels: Administrator, Manager, Staff, and View-Only.
- **Exportable Compliance Reports**: Instant PDF and CSV exports for Expiry Risk, Low Stock, and Valuation audits.

---

## 🛠️ Getting Started

### Prerequisites

- Python 3.10+ or [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- Virtual environment manager (e.g. `uv` or standard `venv`)

### Option A: Local Installation (Recommended for Development)

1.  **Clone the repository** and navigate to the root directory.
2.  **Create and activate a virtual environment**:
    ```bash
    uv venv
    source .venv/bin/activate
    ```
3.  **Install the dependencies**:
    ```bash
    uv sync
    ```
4.  **Run migrations**:
    ```bash
    uv run python manage.py migrate
    ```
5.  **Create an initial Administrator account**:
    ```bash
    python manage.py create_admin  # Or python manage.py createsuperuser
    ```
6.  **Start the development server**:
    ```bash
    python manage.py runserver
    ```
    Access the application at [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Option B: Running via Docker

1.  **Build and launch the containers**:
    ```bash
    docker-compose up --build
    ```
2.  The container will automatically apply migrations and start on [http://localhost:8000](http://localhost:8000).

---

## 👥 Role-Based Access Control (RBAC) Matrix

Users are restricted based on their role:

| Action / Capability                  | Administrator | Manager | Staff | View-Only |
| :----------------------------------- | :-----------: | :-----: | :---: | :-------: |
| **View Dashboard & Listings**        |      ✅       |   ✅    |  ✅   |    ✅     |
| **Download PDF/CSV Reports**         |      ✅       |   ✅    |  ✅   |    ✅     |
| **Add/Edit Products & Locations**    |      ✅       |   ✅    |  ✅   |    ❌     |
| **Acknowledge/Resolve Alerts**       |      ✅       |   ✅    |  ✅   |    ❌     |
| **Delete Products & Locations**      |      ✅       |   ✅    |  ❌   |    ❌     |
| **Configure System APIs & Settings** |      ✅       |   ❌    |  ❌   |    ❌     |

---

## 📈 System Walkthrough & Usage Guide

### 1. Registering Storage Conditions

Before adding batches, navigate to **Storage Locations** to register storage zones with specific temperature and humidity parameters:

- Click **Add Location**, set the parameters (e.g. Temperature: `4.0`°C, Humidity: `45.0`%), and save.

### 2. Creating Products with Initial Batches

Navigate to **Inventory List**:

- Click **Add New Product**.
- Specify **Initial Stock**, **Batch Number**, and select the **Storage Location**.
- Upon saving, the system creates the product record and automatically assigns a tracking `StockBatch` with initial quantities and locations.

### 3. Reviewing Expiry Predictions & Dashboard

When you visit the **Inventory Dashboard**:

1.  The machine learning algorithm pulls the latest inventory parameters and calculates the risk probability.
2.  The interactive **Risk Distribution Chart** updates dynamically.
3.  The **Top Expiry-At-Risk Batches** list highlights items that need immediate attention.

### 4. Acknowledging & Resolving Alerts

If a batch falls into `Critical` (<7 days to expire) or `High` (8-30 days to expire) risk:

1.  The system generates a new record in **Alerts & Audit Log** and sends notification emails/SMS.
2.  Staff can click **Acknowledge** on the Alerts page to update the audit trail and claim ownership.
3.  Once the items are cleared or discarded, click **Resolve & Discard**. This automatically sets the batch quantity to `0`, updates aggregate product stocks, and registers the resolution user and timestamp.

### 5. Exporting Compliance Audits

From either the **Dashboard** or **Alerts & Audit Log** pages, click **Export Report**:

- Select **PDF Document** or **CSV Format**.
- Reports available include: **Expiry Risk Report**, **Low Stock Report**, and **Inventory Valuation**.
