# AI-Based Identity Anomaly Detection System

## Overview

The AI-Based Identity Anomaly Detection System is a User and Entity Behavior Analytics (UEBA) solution designed to detect suspicious authentication activities using Machine Learning. The system analyzes user login behavior in real time to identify identity-based cyber threats such as account takeover, insider threats, privilege abuse, and compromised credentials.

Traditional security systems rely on static rules that are often ineffective against attackers who use legitimate credentials. This project learns normal user behavior and detects deviations using ensemble anomaly detection models, generating risk scores and visualizing suspicious activities through an interactive dashboard.

---

## Objectives

- Develop a machine learning system for real-time identity anomaly detection.
- Learn baseline user behavior from authentication logs.
- Detect suspicious login activities using ensemble anomaly detection.
- Generate dynamic risk scores for authentication events.
- Classify alerts into High, Medium, and Low severity.
- Provide explainable outputs for detected anomalies.
- Visualize security insights through an interactive dashboard.

---

## Features

- Real-time authentication monitoring
- User and Entity Behavior Analytics (UEBA)
- Ensemble anomaly detection
- Dynamic risk score generation
- High, Medium, and Low alert classification
- Explainable anomaly detection
- Interactive Streamlit dashboard
- User behavior visualization
- Risk progression analysis
- Scalable architecture

---

## Machine Learning Models

The system combines multiple anomaly detection algorithms to improve detection accuracy.

- Isolation Forest
- One-Class SVM
- Local Outlier Factor (LOF)
- Elliptic Envelope

The predictions from all models are combined using weighted ensemble scoring to reduce false positives and improve anomaly detection performance.

---

## Behavioral Features

The system analyzes authentication behavior using features such as:

- Login Time
- Device Changes
- Country Changes
- Failed Login Attempts
- Failed-then-Success Login Pattern
- Rapid Consecutive Logins
- Night-Time Access
- Network Latency
- Session Patterns
- Authentication Status

---

## Technology Stack

### Frontend

- Streamlit
- Plotly

### Backend

- Python

### Machine Learning

- Scikit-learn
- Pandas
- NumPy

### Security Monitoring

- auditctl

---

## Dashboard

The dashboard provides the following capabilities:

- User Risk Analysis
- Alert Severity Distribution
- Login Activity Timeline
- Behavioral Trend Analysis
- High-Risk User Identification
- Suspicious Login History
- Model Predictions
- Interactive Charts

---


## System Workflow

Authentication Logs
        │
        ▼
Data Preprocessing
        │
        ▼
Feature Engineering
        │
        ▼
Ensemble Machine Learning Models
        │
        ▼
Risk Score Generation
        │
        ▼
Alert Classification
        │
        ▼
Interactive Dashboard


## Installation

Clone the repository.

bash
git clone https://github.com/yourusername/AI-Based-Identity-Anomaly-Detection-System.git


Move to the project directory.
bash
cd AI-Based-Identity-Anomaly-Detection-System


Install the required packages.

bash
pip install -r requirements.txt

Run the application.

bash
streamlit run app.py



## Future Enhancements

- Autoencoder-based anomaly detection
- LSTM-based behavioral analysis
- Transformer-based anomaly detection
- Real-time SIEM integration
- Microsoft Azure Active Directory integration
- Active Directory monitoring
- Kafka-based log streaming
- Docker deployment
- Cloud deployment on AWS or Azure
- Role-Based Access Control
- Automated incident response

---

## References

- Isolation Forest
- One-Class SVM
- Local Outlier Factor
- Elliptic Envelope
- User and Entity Behavior Analytics
- Enterprise Identity Security Research

---

## Authors

Hemanth Kumar KS

Urvashi Tanwar

Veenashree S T

Vishwanath Sanapur

Department of Computer Science and Engineering

Government Sri Krishnarajendra Silver Jubilee Technological Institute

Visvesvaraya Technological University

---

## License

This project is developed for academic and educational purposes.
