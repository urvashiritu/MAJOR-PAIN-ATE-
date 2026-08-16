import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


import joblib
import numpy as np
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.neighbors import LocalOutlierFactor
from sklearn.covariance import EllipticEnvelope

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)


# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIR = Path("data")
MODEL_DIR = Path("models")
OUTPUT_DIR = Path("outputs")

MODEL_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

TRAIN_RATIO = 0.80

# Heavy models such as One-Class SVM are expensive.
# We train them on at most this many events.
MAX_MODEL_TRAIN_ROWS = 50_000


# ============================================================
# COMMON SCHEMA
# ============================================================

COMMON_COLUMNS = [
    "timestamp",
    "user_id",
    "source_ip",
    "country",
    "region",
    "city",
    "device_type",
    "browser_family",
    "os",
    "success",
    "source",
]


def make_event(
    timestamp=None,
    user_id=None,
    source_ip=None,
    country=None,
    region=None,
    city=None,
    device_type=None,
    browser_family=None,
    os=None,
    success=None,
    source=None,
):
    return {
        "timestamp": timestamp,
        "user_id": user_id,
        "source_ip": source_ip,
        "country": country,
        "region": region,
        "city": city,
        "device_type": device_type,
        "browser_family": browser_family,
        "os": os,
        "success": success,
        "source": source,
    }


# ============================================================
# USER AGENT PARSER
# ============================================================

def parse_user_agent(user_agent):

    if not user_agent:
        return None, None, None

    ua = str(user_agent)

    # Browser
    if "Edg/" in ua:
        browser = "Edge"

    elif "Firefox/" in ua:
        browser = "Firefox"

    elif "Chrome/" in ua and "Mobile" not in ua:
        browser = "Chrome"

    elif "Chrome/" in ua:
        browser = "Chrome Mobile"

    elif "Safari/" in ua:
        browser = "Safari"

    else:
        browser = "Unknown"

    # OS
    if "Windows" in ua:
        os_name = "Windows"

    elif "Android" in ua:
        os_name = "Android"

    elif "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"

    elif "Macintosh" in ua:
        os_name = "macOS"

    elif "Linux" in ua:
        os_name = "Linux"

    else:
        os_name = None

    # Device
    if "iPhone" in ua or "Android" in ua:
        device = "mobile"

    elif "iPad" in ua or "Tablet" in ua:
        device = "tablet"

    else:
        device = "desktop"

    return browser, device, os_name


# ============================================================
# 1. SSH PARSER
# ============================================================

SSH_HEADER = re.compile(
    r"^(?P<ts>\w{3}\s+\d{1,2}\s+\d\d:\d\d:\d\d)"
    r"\s+(?P<host>\S+)"
    r"\s+sshd\[\d+\]:\s+(?P<msg>.*)$"
)

SSH_AUTH = re.compile(
    r"^(?P<action>Accepted|Failed)\s+"
    r"(?P<method>\S+)"
    r"(?:\s+password)?\s+for\s+"
    r"(?:(?:invalid user)\s+)?"
    r"(?P<user>\S+)\s+from\s+"
    r"(?P<ip>[0-9a-fA-F:.]+)\s+port\s+\d+"
)


def parse_ssh():

    rows = []

    path = DATA_DIR / "ssh_auth.log"

    for line in path.open(
        encoding="utf-8",
        errors="replace"
    ):

        match = SSH_HEADER.match(line.strip())

        if not match:
            continue

        auth = SSH_AUTH.match(
            match.group("msg")
        )

        if not auth:
            continue

        # Our generated SSH dataset does not contain
        # a year, so add the dataset year.
        timestamp = (
            "2026 "
            + match.group("ts")
        )

        rows.append(
            make_event(
                timestamp=timestamp,
                user_id=auth.group("user"),
                source_ip=auth.group("ip"),
                os="Linux",
                success=(
                    auth.group("action")
                    == "Accepted"
                ),
                source="SSH",
            )
        )

    return rows


# ============================================================
# 2. WINDOWS ACTIVE DIRECTORY
# ============================================================

def parse_windows():

    rows = []

    path = (
        DATA_DIR /
        "windows_security_events.xml"
    )

    tree = ET.parse(path)
    root = tree.getroot()

    for ev in root:

        if not ev.tag.endswith("Event"):
            continue

        event_id = None
        timestamp = None
        values = {}

        for child in ev:

            tag = child.tag.split("}")[-1]

            if tag == "System":

                for item in child:

                    name = (
                        item.tag.split("}")[-1]
                    )

                    if name == "EventID":
                        event_id = item.text

                    elif name == "TimeCreated":
                        timestamp = (
                            item.attrib.get(
                                "SystemTime"
                            )
                        )

            elif tag == "EventData":

                for item in child:

                    if item.tag.split("}")[-1] == "Data":

                        values[
                            item.attrib.get("Name")
                        ] = item.text

        # 4624 = successful logon
        # 4625 = failed logon

        if event_id not in [
            "4624",
            "4625",
        ]:
            continue

        rows.append(
            make_event(
                timestamp=timestamp,
                user_id=values.get(
                    "TargetUserName"
                ),
                source_ip=values.get(
                    "IpAddress"
                ),
                os="Windows",
                success=(
                    event_id == "4624"
                ),
                source="WINDOWS_AD",
            )
        )

    return rows


# ============================================================
# KEY=VALUE PARSER
# ============================================================

KEY_VALUE = re.compile(
    r'(\w+)=(".*?"|\S+)'
)


def parse_key_value(line):

    result = {}

    for key, value in KEY_VALUE.findall(line):

        if (
            value.startswith('"')
            and value.endswith('"')
        ):
            value = value[1:-1]

        result[key] = value

    return result


# ============================================================
# 3. VPN
# ============================================================

def parse_vpn():

    rows = []

    path = DATA_DIR / "vpn_auth.log"

    for line in path.open(
        encoding="utf-8",
        errors="replace"
    ):

        data = parse_key_value(line)

        if data.get("subtype") != "vpn":
            continue

        timestamp = None

        if (
            data.get("date")
            and data.get("time")
        ):
            timestamp = (
                data["date"]
                + " "
                + data["time"]
            )

        rows.append(
            make_event(
                timestamp=timestamp,
                user_id=data.get("user"),
                source_ip=data.get("remip"),
                country=data.get(
                    "srccountry"
                ),
                success=(
                    data.get("action")
                    == "ssl-login"
                ),
                source="VPN",
            )
        )

    return rows


# ============================================================
# 4. AWS CLOUDTRAIL
# ============================================================

def parse_aws():

    rows = []

    path = (
        DATA_DIR /
        "aws_cloudtrail_console_login.json"
    )

    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    for record in data.get(
        "Records",
        []
    ):

        identity = (
            record.get(
                "userIdentity"
            )
            or {}
        )

        user = (
            identity.get("userName")
            or identity.get("principalId")
            or identity.get("arn")
        )

        response = (
            record.get(
                "responseElements"
            )
            or {}
        )

        success = (
            response.get(
                "ConsoleLogin"
            )
            == "Success"
        )

        browser, device, os_name = (
            parse_user_agent(
                record.get(
                    "userAgent"
                )
            )
        )

        rows.append(
            make_event(
                timestamp=record.get(
                    "eventTime"
                ),
                user_id=user,
                source_ip=record.get(
                    "sourceIPAddress"
                ),
                browser_family=browser,
                device_type=device,
                os=os_name,
                success=success,
                source="AWS",
            )
        )

    return rows


# ============================================================
# 5. MICROSOFT ENTRA / M365
# ============================================================

def parse_m365():

    rows = []

    path = (
        DATA_DIR /
        "entra_signin_logs.json"
    )

    records = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    for record in records:

        device = (
            record.get(
                "deviceDetail"
            )
            or {}
        )

        status = (
            record.get(
                "status"
            )
            or {}
        )

        rows.append(
            make_event(
                timestamp=record.get(
                    "createdDateTime"
                ),
                user_id=record.get(
                    "userPrincipalName"
                ),
                source_ip=record.get(
                    "ipAddress"
                ),
                country=record.get(
                    "location"
                ),
                device_type=device.get(
                    "displayName"
                ),
                browser_family=device.get(
                    "browser"
                ),
                os=device.get(
                    "operatingSystem"
                ),
                success=(
                    status.get(
                        "errorCode"
                    )
                    == 0
                ),
                source="M365",
            )
        )

    return rows


# ============================================================
# 6. MYSQL
# ============================================================

def parse_mysql():

    rows = []

    path = (
        DATA_DIR /
        "mysql_audit_logs.json"
    )

    records = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    for record in records:

        # Startup event is not a login.
        if record.get(
            "event"
        ) != "connect":
            continue

        account = (
            record.get(
                "account"
            )
            or {}
        )

        connection = (
            record.get(
                "connection_data"
            )
            or {}
        )

        attributes = (
            connection.get(
                "connection_attributes"
            )
            or {}
        )

        rows.append(
            make_event(
                timestamp=record.get(
                    "timestamp"
                ),
                user_id=account.get(
                    "user"
                ),
                source_ip=account.get(
                    "ip"
                ),
                os=attributes.get(
                    "_os"
                ),
                success=(
                    connection.get(
                        "status"
                    )
                    == 0
                ),
                source="MYSQL",
            )
        )

    return rows


# ============================================================
# 7. WEB APPLICATION
# ============================================================

def parse_web():

    rows = []

    path = (
        DATA_DIR /
        "web_authentication.jsonl"
    )

    with path.open(
        encoding="utf-8"
    ) as f:

        for line in f:

            if not line.strip():
                continue

            record = json.loads(line)

            browser, device, os_name = (
                parse_user_agent(
                    record.get(
                        "user_agent"
                    )
                )
            )

            rows.append(
                make_event(
                    timestamp=record.get(
                        "datetime"
                    ),
                    user_id=record.get(
                        "userid"
                    ),
                    source_ip=record.get(
                        "source_address"
                    ),
                    device_type=device,
                    browser_family=browser,
                    os=os_name,
                    success=(
                        record.get(
                            "result"
                        )
                        == "SUCCESS"
                    ),
                    source="WEB",
                )
            )

    return rows


# ============================================================
# PARSE ALL DATASETS
# ============================================================

def parse_all():

    parsers = {

        "SSH": parse_ssh,

        "WINDOWS_AD":
            parse_windows,

        "VPN":
            parse_vpn,

        "AWS":
            parse_aws,

        "M365":
            parse_m365,

        "MYSQL":
            parse_mysql,

        "WEB":
            parse_web,
    }

    all_rows = []

    print()
    print("=" * 60)
    print("PARSING DATASETS")
    print("=" * 60)

    for name, parser in parsers.items():

        rows = parser()

        print(
            f"{name:<18}"
            f"{len(rows):>10,}"
        )

        all_rows.extend(rows)

    df = pd.DataFrame(
        all_rows,
        columns=COMMON_COLUMNS
    )

    # Mixed raw timestamp formats are expected.
    # utc=True converts everything to a common timezone.
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        errors="coerce",
        format="mixed",
        utc=True,
    )

    # Normalize success.
    df["success"] = (
        df["success"]
        .fillna(False)
        .astype(bool)
    )

    # Remove unusable events.
    df = df.dropna(
        subset=[
            "timestamp",
            "user_id",
        ]
    )

    # Chronological ordering.
    df = df.sort_values(
        "timestamp"
    ).reset_index(
        drop=True
    )

    print("=" * 60)

    print(
        "TOTAL NORMALIZED EVENTS:",
        f"{len(df):,}"
    )

    output = (
        OUTPUT_DIR /
        "normalized_authentication_events.csv"
    )

    df.to_csv(
        output,
        index=False
    )

    print(
        "Saved:",
        output
    )

    return df


# ============================================================
# BEHAVIORAL FEATURES
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


def create_features(df):

    df = df.copy()

    # --------------------------------------------------------
    # Sort by user and time.
    # Behavioral features depend on history.
    # --------------------------------------------------------

    df = df.sort_values(
        [
            "user_id",
            "timestamp",
        ]
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------

    df["hour"] = (
        df["timestamp"]
        .dt.hour
        .astype(int)
    )

    df["is_night"] = (
        (df["hour"] < 6)
        |
        (df["hour"] >= 22)
    ).astype(int)

    df["is_weekend"] = (
        df["timestamp"]
        .dt.dayofweek >= 5
    ).astype(int)

    # --------------------------------------------------------
    # COUNTRY CHANGE
    # --------------------------------------------------------

    previous_country = (
        df.groupby(
            "user_id"
        )["country"]
        .shift(1)
    )

    df["country_change"] = (
        df["country"].notna()
        &
        previous_country.notna()
        &
        (
            df["country"]
            != previous_country
        )
    ).astype(int)

    # --------------------------------------------------------
    # DEVICE CHANGE
    # --------------------------------------------------------

    previous_device = (
        df.groupby(
            "user_id"
        )["device_type"]
        .shift(1)
    )

    df["device_change"] = (
        df["device_type"].notna()
        &
        previous_device.notna()
        &
        (
            df["device_type"]
            != previous_device
        )
    ).astype(int)

    # --------------------------------------------------------
    # FAILED LOGINS BEFORE CURRENT EVENT
    # --------------------------------------------------------

    failed = (
        ~df["success"]
    ).astype(int)

    df["failed_before_success"] = (
        failed
        .groupby(df["user_id"])
        .transform(
            lambda x:
            x.shift(1)
            .rolling(
                window=10,
                min_periods=1
            )
            .sum()
        )
        .fillna(0)
    )

    # --------------------------------------------------------
    # RAPID LOGIN RATE
    #
    # Number of events for the same user
    # during the previous one hour.
    # --------------------------------------------------------

    df["rapid_login_rate"] = 0.0

    for user_id, indexes in (
        df.groupby(
            "user_id"
        ).groups.items()
    ):

        times = (
            df.loc[indexes, "timestamp"]
            .astype("int64")
            .to_numpy()
        )

        # One hour in nanoseconds.
        window = 60 * 60 * 1_000_000_000

        counts = []

        for i, current_time in enumerate(times):

            left = np.searchsorted(
                times,
                current_time - window,
                side="left"
            )

            counts.append(
                i - left + 1
            )

        df.loc[
            indexes,
            "rapid_login_rate"
        ] = counts

    # --------------------------------------------------------
    # LOGIN FREQUENCY TODAY
    # --------------------------------------------------------

    date = (
        df["timestamp"]
        .dt.date
    )

    df["login_frequency_today"] = (
        df.groupby(
            [
                "user_id",
                date,
            ]
        )["user_id"]
        .transform("count")
    )

    # --------------------------------------------------------
    # MODEL MATRIX
    # --------------------------------------------------------

    X = (
        df[FEATURES]
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
        .fillna(0)
        .astype(float)
    )

    output = (
        OUTPUT_DIR /
        "authentication_features.csv"
    )

    df.to_csv(
        output,
        index=False
    )

    print(
        "\nFeature dataset saved:",
        output
    )

    return df, X


# ============================================================
# ATTACK LABELS
# ============================================================
#
# IMPORTANT:
#
# Our models are UNSUPERVISED.
#
# These labels are NOT used during training.
#
# They are used ONLY for evaluating our synthetic
# test data because we know which IP addresses were
# deliberately generated as suspicious.
#
# ============================================================

ATTACK_IPS = {
    "185.220.101.17",
    "45.155.205.233",
    "91.240.118.172",
    "103.75.201.44",
    "194.26.135.119",
}


def create_evaluation_labels(df):

    labels = (
        df["source_ip"]
        .isin(ATTACK_IPS)
        .astype(int)
    )

    return labels.to_numpy()


# ============================================================
# TRAIN FOUR MODELS
# ============================================================

def train_models(X_train):

    # Computationally expensive models.
    if len(X_train) > MAX_MODEL_TRAIN_ROWS:

        X_model = X_train.sample(
            MAX_MODEL_TRAIN_ROWS,
            random_state=42
        )

    else:

        X_model = X_train

    print()
    print("=" * 60)
    print("MODEL TRAINING")
    print("=" * 60)

    print(
        "Available training events:",
        f"{len(X_train):,}"
    )

    print(
        "Model training sample:",
        f"{len(X_model):,}"
    )

    models = {}

    # --------------------------------------------------------
    # 1. ISOLATION FOREST
    # --------------------------------------------------------

    print(
        "\n[1/4] Training Isolation Forest..."
    )

    isolation_forest = Pipeline([
        (
            "scaler",
            StandardScaler()
        ),
        (
            "model",
            IsolationForest(
                n_estimators=200,
                contamination=0.05,
                random_state=42,
                n_jobs=-1
            )
        )
    ])

    isolation_forest.fit(
        X_model
    )

    models[
        "IsolationForest"
    ] = isolation_forest

    joblib.dump(
        isolation_forest,
        MODEL_DIR /
        "isolation_forest.joblib"
    )

    # --------------------------------------------------------
    # 2. ONE CLASS SVM
    # --------------------------------------------------------

    print(
        "[2/4] Training One-Class SVM..."
    )

    one_class_svm = Pipeline([
        (
            "scaler",
            StandardScaler()
        ),
        (
            "model",
            OneClassSVM(
                kernel="rbf",
                nu=0.05,
                gamma="scale"
            )
        )
    ])

    one_class_svm.fit(
        X_model
    )

    models[
        "OneClassSVM"
    ] = one_class_svm

    joblib.dump(
        one_class_svm,
        MODEL_DIR /
        "one_class_svm.joblib"
    )

    # --------------------------------------------------------
    # 3. LOCAL OUTLIER FACTOR
    # --------------------------------------------------------

    print(
        "[3/4] Training Local Outlier Factor..."
    )

    n_neighbors = min(
        35,
        max(
            5,
            len(X_model) - 1
        )
    )

    lof = Pipeline([
        (
            "scaler",
            StandardScaler()
        ),
        (
            "model",
            LocalOutlierFactor(
                n_neighbors=n_neighbors,
                contamination=0.05,
                novelty=True
            )
        )
    ])

    lof.fit(
        X_model
    )

    models["LOF"] = lof

    joblib.dump(
        lof,
        MODEL_DIR /
        "local_outlier_factor.joblib"
    )

    # --------------------------------------------------------
    # 4. ELLIPTIC ENVELOPE
    # --------------------------------------------------------

    print(
        "[4/4] Training Elliptic Envelope..."
    )

    elliptic = Pipeline([
        (
            "scaler",
            StandardScaler()
        ),
        (
            "model",
            EllipticEnvelope(
                contamination=0.05,
                random_state=42
            )
        )
    ])

    elliptic.fit(
        X_model
    )

    models[
        "EllipticEnvelope"
    ] = elliptic

    joblib.dump(
        elliptic,
        MODEL_DIR /
        "elliptic_envelope.joblib"
    )

    print(
        "\nAll four models trained."
    )

    return models


# ============================================================
# MODEL EVALUATION
# ============================================================

def evaluate_models(
    models,
    X_test,
    y_test
):

    print()
    print("=" * 90)
    print("MODEL EVALUATION")
    print("=" * 90)

    print(
        "Ground-truth attack events:",
        int(y_test.sum())
    )

    print(
        "Normal events:",
        int(
            len(y_test)
            - y_test.sum()
        )
    )

    results = []

    for name, model in models.items():

        # ----------------------------------------------------
        # Binary prediction
        #
        # -1 = anomaly
        # +1 = normal
        # ----------------------------------------------------

        raw_prediction = (
            model.predict(
                X_test
            )
        )

        y_pred = (
            raw_prediction == -1
        ).astype(int)

        # ----------------------------------------------------
        # Continuous anomaly score
        #
        # Lower decision function
        # = more anomalous.
        # ----------------------------------------------------

        decision = (
            model
            .decision_function(
                X_test
            )
        )

        anomaly_score = -decision

        # ----------------------------------------------------
        # Metrics
        # ----------------------------------------------------

        accuracy = accuracy_score(
            y_test,
            y_pred
        )

        precision = precision_score(
            y_test,
            y_pred,
            zero_division=0
        )

        recall = recall_score(
            y_test,
            y_pred,
            zero_division=0
        )

        f1 = f1_score(
            y_test,
            y_pred,
            zero_division=0
        )

        try:

            roc_auc = roc_auc_score(
                y_test,
                anomaly_score
            )

        except ValueError:

            roc_auc = 0.0

        tn, fp, fn, tp = (
            confusion_matrix(
                y_test,
                y_pred,
                labels=[0, 1]
            ).ravel()
        )

        results.append({
            "model": name,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "roc_auc": roc_auc,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "true_positives": tp,
        })

    results_df = pd.DataFrame(
        results
    )

    # F1 is our primary selection metric.
    results_df = (
        results_df
        .sort_values(
            "f1_score",
            ascending=False
        )
        .reset_index(
            drop=True
        )
    )

    # Rank.
    results_df.insert(
        0,
        "rank",
        range(
            1,
            len(results_df) + 1
        )
    )

    print()

    print(
        results_df[
            [
                "rank",
                "model",
                "accuracy",
                "precision",
                "recall",
                "f1_score",
                "roc_auc",
            ]
        ].to_string(
            index=False,
            float_format=lambda x:
            f"{x:.4f}"
        )
    )

    # --------------------------------------------------------
    # BEST MODEL
    # --------------------------------------------------------

    best = results_df.iloc[0]

    print()
    print("=" * 90)
    print("BEST MODEL")
    print("=" * 90)

    print(
        "Model     :",
        best["model"]
    )

    print(
        "F1 Score  :",
        f"{best['f1_score']:.4f}"
    )

    print(
        "Precision :",
        f"{best['precision']:.4f}"
    )

    print(
        "Recall    :",
        f"{best['recall']:.4f}"
    )

    print(
        "Accuracy  :",
        f"{best['accuracy']:.4f}"
    )

    print(
        "ROC-AUC   :",
        f"{best['roc_auc']:.4f}"
    )

    # --------------------------------------------------------
    # SAVE RESULTS
    # --------------------------------------------------------

    evaluation_file = (
        OUTPUT_DIR /
        "model_evaluation.csv"
    )

    results_df.to_csv(
        evaluation_file,
        index=False
    )

    print()
    print(
        "Evaluation saved:",
        evaluation_file
    )

    # Save best model name.
    (
        MODEL_DIR /
        "best_model.txt"
    ).write_text(
        best["model"],
        encoding="utf-8"
    )

    return results_df


# ============================================================
# TEST SET RISK SCORES
# ============================================================

def create_test_risk_scores(
    models,
    X_test,
    test_df
):

    score_columns = {}

    for name, model in models.items():

        decision = (
            model
            .decision_function(
                X_test
            )
        )

        # Convert decision values into
        # relative 0-100 anomaly scores.
        rank = (
            pd.Series(
                decision
            )
            .rank(
                pct=True
            )
            .to_numpy()
        )

        score_columns[name] = (
            1 - rank
        ) * 100

    scores = pd.DataFrame(
        score_columns
    )

    # Ensemble = mean of four model scores.
    scores[
        "ensemble_risk_score"
    ] = scores.mean(
        axis=1
    )

    scores[
        "risk_level"
    ] = pd.cut(
        scores[
            "ensemble_risk_score"
        ],
        bins=[
            -1,
            50,
            75,
            101,
        ],
        labels=[
            "LOW",
            "MEDIUM",
            "HIGH",
        ]
    )

    output = pd.concat(
        [
            test_df.reset_index(
                drop=True
            ),
            scores,
        ],
        axis=1
    )

    output_file = (
        OUTPUT_DIR /
        "test_risk_scores.csv"
    )

    output.to_csv(
        output_file,
        index=False
    )

    print(
        "\nTest risk scores saved:",
        output_file
    )

    return output


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("IDENTITY ANOMALY DETECTION")
    print("=" * 60)

    # ========================================================
    # STEP 1
    # Parse all seven raw datasets.
    # ========================================================

    df = parse_all()

    # ========================================================
    # STEP 2
    # Feature engineering.
    # ========================================================

    print()
    print(
        "=" * 60
    )
    print(
        "FEATURE ENGINEERING"
    )
    print(
        "=" * 60
    )

    feature_df, X = (
        create_features(df)
    )

    print(
        "\nFeatures used:"
    )

    for feature in FEATURES:
        print(
            "  -",
            feature
        )

    # ========================================================
    # STEP 3
    # Train / test split.
    #
    # We use chronological splitting rather than random
    # splitting because this is behavioral/time-series data.
    # ========================================================

    split_index = int(
        len(X)
        * TRAIN_RATIO
    )

    X_train = X.iloc[
        :split_index
    ].copy()

    X_test = X.iloc[
        split_index:
    ].copy()

    df_train = feature_df.iloc[
        :split_index
    ].copy()

    df_test = feature_df.iloc[
        split_index:
    ].copy()

    print()
    print(
        "=" * 60
    )
    print(
        "TRAIN / TEST SPLIT"
    )
    print(
        "=" * 60
    )

    print(
        "Training events:",
        f"{len(X_train):,}"
    )

    print(
        "Testing events :",
        f"{len(X_test):,}"
    )

    # ========================================================
    # STEP 4
    # Create evaluation labels.
    #
    # IMPORTANT:
    # These labels are NOT given to the models.
    # They are only used to evaluate the models.
    # ========================================================

    y_test = create_evaluation_labels(
        df_test
    )

    # ========================================================
    # STEP 5
    # Train four models.
    # ========================================================

    models = train_models(
        X_train
    )

    # ========================================================
    # STEP 6
    # Evaluate.
    # ========================================================

    evaluation = evaluate_models(
        models,
        X_test,
        y_test
    )

    # ========================================================
    # STEP 7
    # Generate ensemble risk scores.
    # ========================================================

    create_test_risk_scores(
        models,
        X_test,
        df_test
    )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    best_model = (
        evaluation.iloc[0]["model"]
    )

    print()
    print("=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    print(
        "Best model:",
        best_model
    )

    print()
    print(
        "Models saved in:",
        MODEL_DIR
    )

    print(
        "Results saved in:",
        OUTPUT_DIR
    )

    print()
    print(
        "Next step: connect the best model"
    )

    print(
        "to live SSH authentication logs."
    )


if __name__ == "__main__":
    main()
