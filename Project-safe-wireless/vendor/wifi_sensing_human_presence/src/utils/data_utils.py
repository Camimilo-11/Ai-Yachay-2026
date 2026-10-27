"""
Data processing utilities for WiFi sensing system.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
from loguru import logger


def load_session_data(session_file: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Load data from a collection session.
    
    Args:
        session_file: Path to session JSON file
        
    Returns:
        Tuple of (dataframe, metadata)
    """
    session_path = Path(session_file)
    
    if not session_path.exists():
        raise FileNotFoundError(f"Session file not found: {session_file}")
    
    # Load session metadata
    with open(session_path, 'r') as f:
        session_data = json.load(f)
    
    metadata = session_data.get("session", {})
    data_files = metadata.get("data_files", [])
    
    if not data_files:
        logger.warning(f"No data files found in session: {session_file}")
        return pd.DataFrame(), metadata
    
    # Load and combine all data files
    all_data_points = []
    
    for data_file in data_files:
        try:
            with open(data_file, 'r') as f:
                data_points = json.load(f)
                all_data_points.extend(data_points)
        except Exception as e:
            logger.warning(f"Could not load data file {data_file}: {e}")
    
    if not all_data_points:
        return pd.DataFrame(), metadata
    
    # Convert to DataFrame
    df = flatten_data_points(all_data_points)
    
    logger.info(f"Loaded {len(df)} data points from session {metadata.get('session_id', 'unknown')}")
    return df, metadata


def flatten_data_points(data_points: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Flatten hierarchical data points into a DataFrame.
    
    Args:
        data_points: List of data point dictionaries
        
    Returns:
        Flattened DataFrame
    """
    rows = []
    
    for dp in data_points:
        row = {
            "timestamp": dp.get("timestamp", 0),
            "session_id": dp.get("session_id", ""),
            "label": dp.get("label", ""),
            "manual_annotation": dp.get("manual_annotation", "")
        }
        
        # Flatten camera data
        camera_data = dp.get("camera_data", {})
        camera_status = camera_data.get("status", {})
        camera_detection = camera_data.get("detection", {})
        
        # Camera status features
        row.update({
            "camera_person_visible": camera_status.get("person_visible", False),
            "camera_time_since_last": camera_status.get("time_since_last_person", 0),
            "camera_frame_count": camera_status.get("frame_count", 0),
            "camera_is_running": camera_status.get("is_running", False)
        })
        
        # Camera detection features
        if camera_detection:
            detections = camera_detection.get("detections", [])
            row.update({
                "camera_detection_count": len(detections),
                "camera_max_confidence": max([d.get("confidence", 0) for d in detections], default=0)
            })
        else:
            row.update({
                "camera_detection_count": 0,
                "camera_max_confidence": 0
            })
        
        # Flatten WiFi features
        wifi_features = dp.get("wifi_features", {})
        for key, value in wifi_features.items():
            if isinstance(value, (int, float)):
                row[f"wifi_{key}"] = value
        
        # WiFi measurements statistics
        wifi_measurements = dp.get("wifi_measurements", [])
        if wifi_measurements:
            signal_strengths = [m.get("signal_strength", 0) for m in wifi_measurements]
            frequencies = [m.get("frequency", 0) for m in wifi_measurements]
            
            row.update({
                "wifi_ap_count": len(wifi_measurements),
                "wifi_signal_mean": np.mean(signal_strengths) if signal_strengths else 0,
                "wifi_signal_std": np.std(signal_strengths) if signal_strengths else 0,
                "wifi_signal_min": np.min(signal_strengths) if signal_strengths else 0,
                "wifi_signal_max": np.max(signal_strengths) if signal_strengths else 0,
                "wifi_freq_mean": np.mean(frequencies) if frequencies else 0,
                "wifi_unique_ssids": len(set(m.get("ssid", "") for m in wifi_measurements))
            })
        else:
            row.update({
                "wifi_ap_count": 0,
                "wifi_signal_mean": 0,
                "wifi_signal_std": 0,
                "wifi_signal_min": 0,
                "wifi_signal_max": 0,
                "wifi_freq_mean": 0,
                "wifi_unique_ssids": 0
            })
        
        rows.append(row)
    
    return pd.DataFrame(rows)


def combine_sessions(session_files: List[str], output_file: Optional[str] = None) -> pd.DataFrame:
    """
    Combine multiple session files into a single DataFrame.
    
    Args:
        session_files: List of session file paths
        output_file: Optional path to save combined data
        
    Returns:
        Combined DataFrame
    """
    combined_data = []
    
    for session_file in session_files:
        try:
            df, metadata = load_session_data(session_file)
            if not df.empty:
                # Add session metadata
                df["source_session"] = metadata.get("session_id", "unknown")
                df["participant_id"] = metadata.get("participant_id", "unknown")
                df["scenario"] = metadata.get("scenario", "unknown")
                df["environment"] = metadata.get("environment", "unknown")
                
                combined_data.append(df)
                
        except Exception as e:
            logger.error(f"Error loading session {session_file}: {e}")
    
    if not combined_data:
        logger.warning("No valid session data found")
        return pd.DataFrame()
    
    # Combine all sessions
    combined_df = pd.concat(combined_data, ignore_index=True)
    
    # Sort by timestamp
    combined_df = combined_df.sort_values("timestamp").reset_index(drop=True)
    
    logger.info(f"Combined {len(combined_data)} sessions into {len(combined_df)} data points")
    
    # Save if requested
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined_df.to_csv(output_file, index=False)
        logger.info(f"Combined data saved to {output_file}")
    
    return combined_df


def clean_data(df: pd.DataFrame, remove_unlabeled: bool = True, 
               min_samples_per_label: int = 10) -> pd.DataFrame:
    """
    Clean and filter the dataset.
    
    Args:
        df: Input DataFrame
        remove_unlabeled: Whether to remove unlabeled samples
        min_samples_per_label: Minimum samples required per label
        
    Returns:
        Cleaned DataFrame
    """
    cleaned_df = df.copy()
    
    logger.info(f"Starting with {len(cleaned_df)} samples")
    
    # Remove rows with missing timestamps
    cleaned_df = cleaned_df.dropna(subset=["timestamp"])
    logger.info(f"After removing missing timestamps: {len(cleaned_df)} samples")
    
    # Remove unlabeled samples if requested
    if remove_unlabeled:
        cleaned_df = cleaned_df[
            (cleaned_df["label"].notna()) & 
            (cleaned_df["label"] != "") & 
            (cleaned_df["label"] != "unknown")
        ]
        logger.info(f"After removing unlabeled: {len(cleaned_df)} samples")
    
    # Check minimum samples per label
    if min_samples_per_label > 0:
        label_counts = cleaned_df["label"].value_counts()
        valid_labels = label_counts[label_counts >= min_samples_per_label].index
        
        removed_labels = set(label_counts.index) - set(valid_labels)
        if removed_labels:
            logger.warning(f"Removing labels with insufficient samples: {removed_labels}")
        
        cleaned_df = cleaned_df[cleaned_df["label"].isin(valid_labels)]
        logger.info(f"After minimum sample filtering: {len(cleaned_df)} samples")
    
    # Remove duplicate timestamps within the same session
    cleaned_df = cleaned_df.drop_duplicates(subset=["timestamp", "session_id"])
    logger.info(f"After removing duplicates: {len(cleaned_df)} samples")
    
    # Fill missing numeric values with 0
    numeric_columns = cleaned_df.select_dtypes(include=[np.number]).columns
    cleaned_df[numeric_columns] = cleaned_df[numeric_columns].fillna(0)
    
    return cleaned_df


def analyze_data_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Analyze data quality and generate report.
    
    Args:
        df: Input DataFrame
        
    Returns:
        Data quality report
    """
    report = {
        "total_samples": len(df),
        "time_span": {},
        "label_distribution": {},
        "missing_data": {},
        "data_quality_issues": []
    }
    
    if df.empty:
        return report
    
    # Time span analysis
    if "timestamp" in df.columns:
        timestamps = pd.to_datetime(df["timestamp"], unit='s')
        report["time_span"] = {
            "start_time": str(timestamps.min()),
            "end_time": str(timestamps.max()),
            "duration_hours": (timestamps.max() - timestamps.min()).total_seconds() / 3600,
            "sampling_rate_hz": len(df) / max((timestamps.max() - timestamps.min()).total_seconds(), 1)
        }
    
    # Label distribution
    if "label" in df.columns:
        label_counts = df["label"].value_counts()
        report["label_distribution"] = label_counts.to_dict()
        
        # Check for imbalanced classes
        min_count = label_counts.min()
        max_count = label_counts.max()
        if max_count > 10 * min_count:
            report["data_quality_issues"].append(f"Class imbalance detected: {max_count}:{min_count} ratio")
    
    # Missing data analysis
    missing_data = {}
    for column in df.columns:
        missing_count = df[column].isna().sum()
        if missing_count > 0:
            missing_data[column] = {
                "count": int(missing_count),
                "percentage": float(missing_count / len(df) * 100)
            }
    
    report["missing_data"] = missing_data
    
    # Data quality checks
    if "camera_person_visible" in df.columns:
        visible_ratio = df["camera_person_visible"].mean()
        if visible_ratio > 0.8:
            report["data_quality_issues"].append("High camera visibility ratio - may lack hidden presence samples")
        elif visible_ratio < 0.1:
            report["data_quality_issues"].append("Low camera visibility ratio - may lack visible presence samples")
    
    if "wifi_ap_count" in df.columns:
        zero_wifi_ratio = (df["wifi_ap_count"] == 0).mean()
        if zero_wifi_ratio > 0.5:
            report["data_quality_issues"].append("High ratio of samples with no WiFi data")
    
    logger.info(f"Data quality analysis complete. Found {len(report['data_quality_issues'])} issues")
    
    return report


def export_for_ml(df: pd.DataFrame, feature_columns: Optional[List[str]] = None,
                 label_column: str = "label", output_dir: str = "data/processed") -> Dict[str, str]:
    """
    Export data in format suitable for ML training.
    
    Args:
        df: Input DataFrame
        feature_columns: List of feature columns (auto-detect if None)
        label_column: Name of label column
        output_dir: Output directory
        
    Returns:
        Dictionary of output file paths
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Auto-detect feature columns if not provided
    if feature_columns is None:
        exclude_columns = {
            "timestamp", "session_id", label_column, "manual_annotation",
            "source_session", "participant_id", "scenario", "environment"
        }
        feature_columns = [col for col in df.columns if col not in exclude_columns]
    
    # Create feature matrix and labels
    X = df[feature_columns]
    y = df[label_column]
    
    # Save feature data
    features_file = output_path / "features.csv"
    X.to_csv(features_file, index=False)
    
    # Save labels
    labels_file = output_path / "labels.csv"
    y.to_csv(labels_file, index=False)
    
    # Save full dataset
    full_file = output_path / "full_dataset.csv"
    df.to_csv(full_file, index=False)
    
    # Save feature names
    feature_names_file = output_path / "feature_names.json"
    with open(feature_names_file, 'w') as f:
        json.dump(feature_columns, f, indent=2)
    
    # Save metadata
    metadata = {
        "total_samples": len(df),
        "num_features": len(feature_columns),
        "feature_columns": feature_columns,
        "label_column": label_column,
        "label_classes": sorted(y.unique().tolist()),
        "export_timestamp": pd.Timestamp.now().isoformat()
    }
    
    metadata_file = output_path / "metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    output_files = {
        "features": str(features_file),
        "labels": str(labels_file),
        "full_dataset": str(full_file),
        "feature_names": str(feature_names_file),
        "metadata": str(metadata_file)
    }
    
    logger.info(f"ML data exported to {output_dir} with {len(feature_columns)} features")
    
    return output_files


def main():
    """Example usage of data processing utilities."""
    # This would be used to process collected data
    
    # Example: Load and combine sessions
    session_files = [
        "data/raw/session_001_session.json",
        "data/raw/session_002_session.json"
    ]
    
    # In a real scenario, these files would exist
    print("Example data processing workflow:")
    print("1. Load session data: load_session_data('session_file.json')")
    print("2. Combine sessions: combine_sessions(session_files)")
    print("3. Clean data: clean_data(df)")
    print("4. Analyze quality: analyze_data_quality(df)")
    print("5. Export for ML: export_for_ml(df)")


if __name__ == "__main__":
    main()