#!/usr/bin/env python3
"""
Model training script for WiFi sensing human presence detection.

This script processes collected data and trains machine learning models
for presence classification.
"""

import sys
import argparse
from pathlib import Path
import json

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from src.ml import MLPipeline
from src.utils import ConfigLoader, setup_logging, load_session_data, combine_sessions, clean_data, analyze_data_quality
from loguru import logger


def main():
    """Main training script."""
    parser = argparse.ArgumentParser(description="Train WiFi sensing models")
    parser.add_argument("--config", "-c", default="config/config.yaml",
                       help="Configuration file")
    parser.add_argument("--data-dir", "-d", default="data/raw",
                       help="Directory containing session data")
    parser.add_argument("--output-dir", "-o", default="data/processed",
                       help="Output directory for processed data")
    parser.add_argument("--model-type", "-m", choices=["random_forest", "svm", "neural_network"],
                       default="random_forest", help="Model type to train")
    parser.add_argument("--tune-hyperparameters", action="store_true",
                       help="Perform hyperparameter tuning")
    parser.add_argument("--validate", action="store_true", default=True,
                       help="Perform validation")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level="INFO")
    logger.info("Starting model training")
    
    # Load configuration
    config_loader = ConfigLoader()
    config = config_loader.load_config(args.config)
    
    # Override model type
    config["ml"]["model"]["type"] = args.model_type
    
    # Find session files
    data_dir = Path(args.data_dir)
    session_files = list(data_dir.glob("*_session.json"))
    
    if not session_files:
        logger.error(f"No session files found in {data_dir}")
        sys.exit(1)
    
    logger.info(f"Found {len(session_files)} session files")
    
    # Combine sessions
    logger.info("Loading and combining session data...")
    combined_df = combine_sessions([str(f) for f in session_files])
    
    if combined_df.empty:
        logger.error("No valid data found in sessions")
        sys.exit(1)
    
    # Analyze data quality
    logger.info("Analyzing data quality...")
    quality_report = analyze_data_quality(combined_df)
    
    logger.info(f"Data quality report:")
    logger.info(f"  Total samples: {quality_report['total_samples']}")
    logger.info(f"  Label distribution: {quality_report['label_distribution']}")
    logger.info(f"  Quality issues: {len(quality_report['data_quality_issues'])}")
    
    for issue in quality_report['data_quality_issues']:
        logger.warning(f"  - {issue}")
    
    # Clean data
    logger.info("Cleaning data...")
    clean_df = clean_data(combined_df, remove_unlabeled=True, min_samples_per_label=10)
    
    logger.info(f"After cleaning: {len(clean_df)} samples")
    
    if len(clean_df) < 50:
        logger.error("Insufficient data for training (need at least 50 samples)")
        sys.exit(1)
    
    # Save processed data
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    processed_file = output_dir / "training_data.csv"
    clean_df.to_csv(processed_file, index=False)
    logger.info(f"Processed data saved to {processed_file}")
    
    # Initialize ML pipeline
    logger.info(f"Initializing ML pipeline with {args.model_type}")
    pipeline = MLPipeline(config["ml"])
    
    # Prepare features and labels
    exclude_cols = {"timestamp", "session_id", "manual_annotation", 
                   "source_session", "participant_id", "scenario", "environment"}
    feature_cols = [col for col in clean_df.columns if col not in exclude_cols and col != "label"]
    
    features_df = clean_df[feature_cols]
    labels = clean_df["label"].tolist()
    
    logger.info(f"Training with {len(feature_cols)} features")
    logger.info(f"Feature columns: {feature_cols[:10]}...")  # Show first 10
    
    # Train model
    logger.info("Starting model training...")
    results = pipeline.trainer.train(
        features_df, 
        labels,
        validate=args.validate,
        tune_hyperparameters=args.tune_hyperparameters
    )
    
    # Print results
    logger.info("Training completed!")
    logger.info(f"Training time: {results.get('training_time', 0):.2f}s")
    
    if args.validate:
        logger.info(f"Test accuracy: {results.get('test_accuracy', 0):.3f}")
        logger.info(f"CV accuracy: {results.get('cv_mean', 0):.3f} ± {results.get('cv_std', 0):.3f}")
    
    # Save model
    model_filename = f"{args.model_type}_model.joblib"
    model_path = Path("models") / model_filename
    model_path.parent.mkdir(exist_ok=True)
    
    pipeline.trainer.save_model(str(model_path))
    logger.info(f"Model saved to {model_path}")
    
    # Save training results
    results_file = output_dir / f"{args.model_type}_training_results.json"
    with open(results_file, 'w') as f:
        # Convert numpy arrays to lists for JSON serialization
        serializable_results = {}
        for key, value in results.items():
            if hasattr(value, 'tolist'):
                serializable_results[key] = value.tolist()
            else:
                serializable_results[key] = value
        
        json.dump(serializable_results, f, indent=2)
    
    logger.info(f"Training results saved to {results_file}")
    
    # Generate plots if validation was performed
    if args.validate and "confusion_matrix" in results:
        plot_path = output_dir / f"{args.model_type}_training_plots.png"
        pipeline.trainer.plot_training_results(results, str(plot_path))


if __name__ == "__main__":
    main()