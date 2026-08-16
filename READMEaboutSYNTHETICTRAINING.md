# Identity Anomaly Detection

Multi-source authentication anomaly detection using machine learning.

## Requirements

- Python 3.10+
- Linux recommended
- Git

## Dataset

All datasets must be kept inside the `data/` directory:

```text
data/
├── ssh_auth.log
├── windows_security_events.xml
├── vpn_auth.log
├── aws_cloudtrail_console_login.json
├── entra_signin_logs.json
├── mysql_audit_logs.json
└── web_authentication.jsonl

These are synthetic datasets created to mimic the structure and format of real authentication logs.

They are used for:

Parser testing
Data normalization
Model training
Model evaluation
Project demonstration

Do not change the dataset file formats unless the corresponding parser is also updated.

Setup

Clone the repository:

git clone <repository-url>
cd finalproject

Create a virtual environment:

python -m venv .venv
source .venv/bin/activate

Install dependencies:

pip install pandas numpy scikit-learn joblib plotly streamlit
Train the Models

Run:

python train.py

The training pipeline is:

Raw Datasets
     ↓
Parsers
     ↓
Normalized Data
     ↓
Feature Extraction
     ↓
Model Training
     ↓
Model Evaluation

The trained models are saved in:

models/

Training and evaluation results are saved in:

outputs/
Run the Dashboard

After training, run:

streamlit run dashboard.py

Open the URL shown by Streamlit, usually:

http://localhost:8501

The dashboard provides:

Dataset and parsing information
Model performance
Anomaly statistics
Live SSH monitoring
Live SSH Demo

The live SSH detector monitors:

/var/log/auth.log

To generate an SSH authentication event, use:

ssh localhost

You can also use the Trigger Failed SSH Attempt button in the dashboard.

Important

Do not commit real company authentication logs, passwords, API keys, tokens, or other sensitive security information to this repository.
