import re
import time
from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

MODEL_DIR = Path("models")

# Start with our synthetic SSH log.
# After testing, change this to /var/log/auth.log
LOG_FILE = Path("/var/log/auth.log")

# How many previous events to remember per user.
HISTORY_SIZE = 100

# Event window for rapid-login calculation.
RAPID_WINDOW_SECONDS = 60 * 60


# ============================================================
# SSH PARSER
# ============================================================

SSH_HEADER = re.compile(
    r"^(?P<ts>\S+)"
    r"\s+(?P<host>\S+)"
    r"\s+sshd(?:-session)?\[\d+\]:\s+"
    r"(?P<msg>.*)$"
)

SSH_AUTH = re.compile(
    r"^(?P<action>Accepted|Failed)\s+"
    r"(?P<method>\S+)"
    r"(?:\s+password)?\s+for\s+"
    r"(?:(?:invalid user)\s+)?"
    r"(?P<user>\S+)\s+from\s+"
    r"(?P<ip>[0-9a-fA-F:.]+)\s+port\s+\d+"
)

def parse_ssh_line(line):

    match = SSH_HEADER.match(line.strip())

    if not match:
        return None

    auth = SSH_AUTH.match(
        match.group("msg")
    )

    if not auth:
        return None

    timestamp = (
        "2026 "
        + match.group("ts")
    )

    timestamp = pd.to_datetime(
        match.group("ts"),
        utc=True
    )

    return {
        "timestamp": timestamp,
        "user_id": auth.group("user"),
        "source_ip": auth.group("ip"),
        "success": (
            auth.group("action")
            == "Accepted"
        ),
        "source": "SSH",
        "os": "Linux",
    }


# ============================================================
# USER HISTORY
# ============================================================

user_history = defaultdict(
    lambda: deque(
        maxlen=HISTORY_SIZE
    )
)


# ============================================================
# FEATURE EXTRACTION
# ============================================================

FEATURES = [
    "hour",
    "is_night",
    "is_weekend",
    "country_change",
    "device_change",
    "failed_before_success",
    "rapid_login_rate",
    "login_frequency_today",
]


def calculate_features(event):

    user = event["user_id"]
    timestamp = event["timestamp"]

    history = user_history[user]

    # --------------------------------------------------------
    # TIME FEATURES
    # --------------------------------------------------------

    hour = timestamp.hour

    is_night = int(
        hour < 6 or hour >= 22
    )

    is_weekend = int(
        timestamp.weekday() >= 5
    )

    # --------------------------------------------------------
    # SSH DOES NOT PROVIDE COUNTRY OR DEVICE.
    #
    # Therefore these are unavailable for the SSH source.
    # We use 0 rather than inventing values.
    # --------------------------------------------------------

    country_change = 0
    device_change = 0

    # --------------------------------------------------------
    # FAILED LOGINS BEFORE CURRENT EVENT
    # --------------------------------------------------------

    recent_events = list(history)

    failed_before_success = sum(
        1
        for previous in recent_events[-10:]
        if not previous["success"]
    )

    # --------------------------------------------------------
    # RAPID LOGIN RATE
    # --------------------------------------------------------

    rapid_login_rate = sum(
        1
        for previous in recent_events
        if (
            timestamp
            - previous["timestamp"]
        ).total_seconds()
        <= RAPID_WINDOW_SECONDS
    )

    # Include current event.
    rapid_login_rate += 1

    # --------------------------------------------------------
    # LOGIN FREQUENCY TODAY
    # --------------------------------------------------------

    current_date = timestamp.date()

    login_frequency_today = sum(
        1
        for previous in recent_events
        if previous["timestamp"].date()
        == current_date
    )

    login_frequency_today += 1

    values = [
        hour,
        is_night,
        is_weekend,
        country_change,
        device_change,
        failed_before_success,
        rapid_login_rate,
        login_frequency_today,
    ]

    return np.array(
        [values],
        dtype=float
    )


# ============================================================
# LOAD BEST MODEL
# ============================================================

best_model_file = (
    MODEL_DIR /
    "best_model.txt"
)

if not best_model_file.exists():

    raise FileNotFoundError(
        "models/best_model.txt not found. "
        "Run train.py first."
    )

best_model_name = (
    best_model_file
    .read_text()
    .strip()
)

MODEL_FILES = {
    "IsolationForest":
        "isolation_forest.joblib",

    "OneClassSVM":
        "one_class_svm.joblib",

    "LOF":
        "local_outlier_factor.joblib",

    "EllipticEnvelope":
        "elliptic_envelope.joblib",
}

if best_model_name not in MODEL_FILES:

    raise ValueError(
        f"Unknown model: {best_model_name}"
    )

model_path = (
    MODEL_DIR /
    MODEL_FILES[
        best_model_name
    ]
)

model = joblib.load(
    model_path
)


# ============================================================
# RISK SCORE
# ============================================================

def calculate_risk(
    decision_value
):

    # Models return:
    #
    # higher decision value = more normal
    # lower decision value = more anomalous
    #
    # For a live demo we convert it to a
    # simple relative 0-100 score.

    # Logistic transformation.
    risk = (
        100 /
        (
            1
            +
            np.exp(
                np.clip(
                    decision_value * 5,
                    -50,
                    50
                )
            )
        )
    )

    return float(
        np.clip(
            risk,
            0,
            100
        )
    )


def risk_level(score):

    if score >= 75:
        return "HIGH"

    if score >= 50:
        return "MEDIUM"

    return "LOW"


# ============================================================
# PROCESS EVENT
# ============================================================

def process_event(event):

    features = calculate_features(
        event
    )

    prediction = model.predict(
        features
    )[0]

    decision = model.decision_function(
        features
    )[0]

    risk = calculate_risk(
        decision
    )

    level = risk_level(
        risk
    )

    # Store event AFTER calculating
    # features so it does not affect
    # its own historical features.
    user_history[
        event["user_id"]
    ].append(event)

    print()
    print("=" * 65)

    print(
        f"USER       : {event['user_id']}"
    )

    print(
        f"IP         : {event['source_ip']}"
    )

    print(
        f"TIME       : "
        f"{event['timestamp']}"
    )

    print(
        f"LOGIN      : "
        f"{'SUCCESS' if event['success'] else 'FAILED'}"
    )

    print(
        f"MODEL      : "
        f"{best_model_name}"
    )

    print(
        f"ANOMALY    : "
        f"{'YES' if prediction == -1 else 'NO'}"
    )

    print(
        f"RISK SCORE : "
        f"{risk:.2f}/100"
    )

    print(
        f"RISK LEVEL : "
        f"{level}"
    )

    print(
        "FEATURES   :"
    )

    for name, value in zip(
        FEATURES,
        features[0]
    ):

        print(
            f"  {name:<25}: {value}"
        )

    if level == "HIGH":

        print()
        print(
            "!!! HIGH-RISK SSH LOGIN DETECTED !!!"
        )

    print("=" * 65)


# ============================================================
# PROCESS EXISTING FILE
# ============================================================

def process_existing_file():

    print()
    print("=" * 65)
    print("LIVE SSH DETECTION")
    print("=" * 65)

    print(
        f"Model : {best_model_name}"
    )

    print(
        f"Input : {LOG_FILE}"
    )

    print()

    with LOG_FILE.open(
        encoding="utf-8",
        errors="replace"
    ) as f:

        for line in f:

            event = parse_ssh_line(
                line
            )

            if event:

                process_event(
                    event
                )


# ============================================================
# LIVE TAIL MODE
# ============================================================

def follow_live_log():

    print()
    print("=" * 65)
    print("LIVE SSH LOG MONITOR")
    print("=" * 65)

    print(
        f"Monitoring: {LOG_FILE}"
    )

    print(
        f"Model: {best_model_name}"
    )

    print(
        "\nWaiting for new SSH authentication events..."
    )

    with LOG_FILE.open(
        "r",
        encoding="utf-8",
        errors="replace"
    ) as f:

        # Jump to end of file.
        f.seek(0, 2)

        while True:

            line = f.readline()

            if not line:

                time.sleep(0.5)
                continue

            event = parse_ssh_line(
                line
            )

            if event:

                process_event(
                    event
                )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print(
        "\nChoose mode:"
    )

    print(
        "1. Process existing SSH dataset"
    )

    print(
        "2. Monitor live SSH log"
    )

    choice = input(
        "\nEnter choice [1/2]: "
    ).strip()

    if choice == "1":

        process_existing_file()

    elif choice == "2":

        follow_live_log()

    else:

        print(
            "Invalid choice."
        )
