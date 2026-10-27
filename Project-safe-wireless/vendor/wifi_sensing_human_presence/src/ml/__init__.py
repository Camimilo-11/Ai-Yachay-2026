"""
Machine learning module for WiFi-based human presence detection.

This module provides training and inference capabilities for classifying
human presence states using WiFi signal features.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple, Union
import joblib
from pathlib import Path
import time
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from loguru import logger
import matplotlib.pyplot as plt
import seaborn as sns


class DataPreprocessor:
    """Preprocessing pipeline for WiFi features and labels."""
    
    def __init__(self):
        """Initialize preprocessor."""
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.feature_columns = None
        self.is_fitted = False
        
    def fit(self, features_df: pd.DataFrame, labels: List[str]):
        """
        Fit the preprocessor on training data.
        
        Args:
            features_df: DataFrame with WiFi features
            labels: List of presence state labels
        """
        # Store feature columns
        self.feature_columns = features_df.columns.tolist()
        
        # Fit scaler on numeric features
        numeric_features = features_df.select_dtypes(include=[np.number])
        self.scaler.fit(numeric_features)
        
        # Fit label encoder
        self.label_encoder.fit(labels)
        
        self.is_fitted = True
        logger.info(f"Preprocessor fitted on {len(features_df)} samples with {len(self.feature_columns)} features")
    
    def transform(self, features_df: pd.DataFrame, 
                  labels: Optional[List[str]] = None) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Transform features and labels.
        
        Args:
            features_df: DataFrame with WiFi features
            labels: Optional list of labels
            
        Returns:
            Tuple of (transformed_features, transformed_labels)
        """
        if not self.is_fitted:
            raise ValueError("Preprocessor must be fitted before transform")
        
        # Ensure all required columns are present
        missing_cols = set(self.feature_columns) - set(features_df.columns)
        for col in missing_cols:
            features_df[col] = 0.0
        
        # Select and order columns as in training
        features_df = features_df[self.feature_columns]
        
        # Scale features
        numeric_features = features_df.select_dtypes(include=[np.number])
        scaled_features = self.scaler.transform(numeric_features)
        
        # Transform labels if provided
        transformed_labels = None
        if labels is not None:
            transformed_labels = self.label_encoder.transform(labels)
        
        return scaled_features, transformed_labels
    
    def inverse_transform_labels(self, encoded_labels: np.ndarray) -> List[str]:
        """Convert encoded labels back to original strings."""
        return self.label_encoder.inverse_transform(encoded_labels).tolist()
    
    def save(self, filepath: str):
        """Save preprocessor to file."""
        preprocessor_data = {
            'scaler': self.scaler,
            'label_encoder': self.label_encoder,
            'feature_columns': self.feature_columns,
            'is_fitted': self.is_fitted
        }
        joblib.dump(preprocessor_data, filepath)
        logger.info(f"Preprocessor saved to {filepath}")
    
    def load(self, filepath: str):
        """Load preprocessor from file."""
        preprocessor_data = joblib.load(filepath)
        self.scaler = preprocessor_data['scaler']
        self.label_encoder = preprocessor_data['label_encoder']
        self.feature_columns = preprocessor_data['feature_columns']
        self.is_fitted = preprocessor_data['is_fitted']
        logger.info(f"Preprocessor loaded from {filepath}")


class ModelTrainer:
    """Train and evaluate machine learning models for presence detection."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize model trainer.
        
        Args:
            config: Training configuration
        """
        self.config = config
        self.model_type = config.get("type", "random_forest")
        self.preprocessor = DataPreprocessor()
        
        # Model configurations
        self.model_configs = {
            "random_forest": config.get("random_forest", {
                "n_estimators": 100,
                "max_depth": 10,
                "random_state": 42
            }),
            "svm": config.get("svm", {
                "kernel": "rbf",
                "C": 1.0,
                "gamma": "scale",
                "random_state": 42
            }),
            "neural_network": config.get("neural_network", {
                "hidden_layer_sizes": (64, 32, 16),
                "learning_rate_init": 0.001,
                "max_iter": 1000,
                "random_state": 42
            })
        }
        
        # Training settings
        self.test_size = config.get("training", {}).get("test_size", 0.2)
        self.validation_size = config.get("training", {}).get("validation_size", 0.1)
        self.cv_folds = config.get("training", {}).get("cross_validation_folds", 5)
        
        self.model = None
        self.training_history = {}
        
        logger.info(f"Model trainer initialized for {self.model_type}")
    
    def create_model(self) -> Any:
        """Create and return model instance."""
        if self.model_type == "random_forest":
            return RandomForestClassifier(**self.model_configs["random_forest"])
        elif self.model_type == "svm":
            return SVC(**self.model_configs["svm"], probability=True)
        elif self.model_type == "neural_network":
            return MLPClassifier(**self.model_configs["neural_network"])
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
    
    def train(self, features_df: pd.DataFrame, labels: List[str], 
              validate: bool = True, tune_hyperparameters: bool = False) -> Dict[str, Any]:
        """
        Train the model on provided data.
        
        Args:
            features_df: DataFrame with WiFi features
            labels: List of presence state labels
            validate: Whether to perform validation
            tune_hyperparameters: Whether to tune hyperparameters
            
        Returns:
            Training results dictionary
        """
        logger.info(f"Training {self.model_type} model on {len(features_df)} samples")
        
        # Fit preprocessor
        self.preprocessor.fit(features_df, labels)
        
        # Transform data
        X, y = self.preprocessor.transform(features_df, labels)
        
        # Split data
        if validate:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=self.test_size, 
                random_state=42, stratify=y
            )
        else:
            X_train, X_test, y_train, y_test = X, None, y, None
        
        # Hyperparameter tuning if requested
        if tune_hyperparameters:
            self.model = self._tune_hyperparameters(X_train, y_train)
        else:
            self.model = self.create_model()
        
        # Train model
        start_time = time.time()
        self.model.fit(X_train, y_train)
        training_time = time.time() - start_time
        
        # Evaluate model
        results = {
            "training_time": training_time,
            "training_samples": len(X_train),
            "model_type": self.model_type
        }
        
        if validate and X_test is not None:
            results.update(self._evaluate_model(X_test, y_test, X_train, y_train))
        
        # Cross-validation
        if validate:
            cv_scores = cross_val_score(self.model, X_train, y_train, cv=self.cv_folds)
            results["cv_scores"] = cv_scores.tolist()
            results["cv_mean"] = cv_scores.mean()
            results["cv_std"] = cv_scores.std()
        
        self.training_history[time.time()] = results
        
        logger.info(f"Training completed in {training_time:.2f}s")
        if validate:
            logger.info(f"Test accuracy: {results.get('test_accuracy', 0):.3f}")
            logger.info(f"CV accuracy: {results.get('cv_mean', 0):.3f} ± {results.get('cv_std', 0):.3f}")
        
        return results
    
    def _tune_hyperparameters(self, X_train: np.ndarray, y_train: np.ndarray) -> Any:
        """Tune model hyperparameters using grid search."""
        logger.info("Tuning hyperparameters...")
        
        param_grids = {
            "random_forest": {
                "n_estimators": [50, 100, 200],
                "max_depth": [5, 10, 15, None],
                "min_samples_split": [2, 5, 10]
            },
            "svm": {
                "C": [0.1, 1, 10, 100],
                "gamma": ["scale", "auto", 0.001, 0.01]
            },
            "neural_network": {
                "hidden_layer_sizes": [(32,), (64,), (64, 32), (128, 64, 32)],
                "learning_rate_init": [0.001, 0.01, 0.1]
            }
        }
        
        base_model = self.create_model()
        param_grid = param_grids.get(self.model_type, {})
        
        if param_grid:
            grid_search = GridSearchCV(
                base_model, param_grid, cv=3, 
                scoring="accuracy", n_jobs=-1, verbose=1
            )
            grid_search.fit(X_train, y_train)
            
            logger.info(f"Best parameters: {grid_search.best_params_}")
            logger.info(f"Best CV score: {grid_search.best_score_:.3f}")
            
            return grid_search.best_estimator_
        else:
            logger.warning(f"No parameter grid defined for {self.model_type}")
            return base_model
    
    def _evaluate_model(self, X_test: np.ndarray, y_test: np.ndarray,
                       X_train: np.ndarray, y_train: np.ndarray) -> Dict[str, Any]:
        """Evaluate model performance."""
        # Predictions
        y_train_pred = self.model.predict(X_train)
        y_test_pred = self.model.predict(X_test)
        
        # Probabilities
        y_test_proba = self.model.predict_proba(X_test)
        
        # Metrics
        train_accuracy = accuracy_score(y_train, y_train_pred)
        test_accuracy = accuracy_score(y_test, y_test_pred)
        
        # Classification report
        label_names = self.preprocessor.label_encoder.classes_
        class_report = classification_report(
            y_test, y_test_pred, 
            target_names=label_names, 
            output_dict=True
        )
        
        # Confusion matrix
        cm = confusion_matrix(y_test, y_test_pred)
        
        return {
            "train_accuracy": train_accuracy,
            "test_accuracy": test_accuracy,
            "classification_report": class_report,
            "confusion_matrix": cm.tolist(),
            "test_predictions": y_test_pred.tolist(),
            "test_probabilities": y_test_proba.tolist(),
            "label_names": label_names.tolist()
        }
    
    def predict(self, features_df: pd.DataFrame) -> Tuple[List[str], np.ndarray]:
        """
        Make predictions on new data.
        
        Args:
            features_df: DataFrame with WiFi features
            
        Returns:
            Tuple of (predicted_labels, prediction_probabilities)
        """
        if self.model is None:
            raise ValueError("Model must be trained before prediction")
        
        X, _ = self.preprocessor.transform(features_df)
        
        # Make predictions
        y_pred = self.model.predict(X)
        y_proba = self.model.predict_proba(X)
        
        # Convert back to original labels
        predicted_labels = self.preprocessor.inverse_transform_labels(y_pred)
        
        return predicted_labels, y_proba
    
    def save_model(self, filepath: str):
        """Save trained model and preprocessor."""
        if self.model is None:
            raise ValueError("No trained model to save")
        
        model_data = {
            "model": self.model,
            "preprocessor": self.preprocessor,
            "config": self.config,
            "training_history": self.training_history,
            "feature_columns": self.preprocessor.feature_columns,
            "label_classes": self.preprocessor.label_encoder.classes_.tolist()
        }
        
        joblib.dump(model_data, filepath)
        logger.info(f"Model saved to {filepath}")
    
    def load_model(self, filepath: str):
        """Load trained model and preprocessor."""
        model_data = joblib.load(filepath)
        
        self.model = model_data["model"]
        self.preprocessor = model_data["preprocessor"]
        self.training_history = model_data.get("training_history", {})
        
        logger.info(f"Model loaded from {filepath}")
    
    def plot_training_results(self, results: Dict[str, Any], save_path: Optional[str] = None):
        """Plot training results and confusion matrix."""
        if "confusion_matrix" not in results:
            logger.warning("No confusion matrix in results to plot")
            return
        
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        
        # Confusion Matrix
        cm = np.array(results["confusion_matrix"])
        label_names = results.get("label_names", [f"Class {i}" for i in range(len(cm))])
        
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                   xticklabels=label_names, yticklabels=label_names, ax=axes[0])
        axes[0].set_title('Confusion Matrix')
        axes[0].set_xlabel('Predicted')
        axes[0].set_ylabel('Actual')
        
        # Metrics Bar Plot
        metrics = []
        values = []
        
        if "cv_mean" in results:
            metrics.append("CV Accuracy")
            values.append(results["cv_mean"])
        
        if "test_accuracy" in results:
            metrics.append("Test Accuracy")
            values.append(results["test_accuracy"])
        
        if "train_accuracy" in results:
            metrics.append("Train Accuracy")
            values.append(results["train_accuracy"])
        
        if metrics:
            axes[1].bar(metrics, values)
            axes[1].set_title('Model Performance Metrics')
            axes[1].set_ylabel('Accuracy')
            axes[1].set_ylim(0, 1)
            
            # Add value labels on bars
            for i, v in enumerate(values):
                axes[1].text(i, v + 0.01, f'{v:.3f}', ha='center', va='bottom')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"Training plots saved to {save_path}")
        
        plt.show()


class MLPipeline:
    """End-to-end machine learning pipeline."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize ML pipeline."""
        self.config = config
        self.trainer = ModelTrainer(config)
        self.models_dir = Path(config.get("models_dir", "models"))
        self.models_dir.mkdir(exist_ok=True)
        
    def train_from_data_files(self, data_files: List[str], 
                             label_column: str = "label",
                             validate: bool = True,
                             tune_hyperparameters: bool = False) -> Dict[str, Any]:
        """
        Train model from data files.
        
        Args:
            data_files: List of paths to data files (CSV or similar)
            label_column: Name of the label column
            validate: Whether to perform validation
            tune_hyperparameters: Whether to tune hyperparameters
            
        Returns:
            Training results
        """
        # Load and combine data
        all_features = []
        all_labels = []
        
        for data_file in data_files:
            logger.info(f"Loading data from {data_file}")
            
            if data_file.endswith('.csv'):
                df = pd.read_csv(data_file)
            elif data_file.endswith('.json'):
                df = pd.read_json(data_file)
            else:
                logger.warning(f"Unsupported file format: {data_file}")
                continue
            
            if label_column not in df.columns:
                logger.warning(f"Label column '{label_column}' not found in {data_file}")
                continue
            
            # Separate features and labels
            features = df.drop(columns=[label_column])
            labels = df[label_column].tolist()
            
            all_features.append(features)
            all_labels.extend(labels)
        
        if not all_features:
            raise ValueError("No valid data files loaded")
        
        # Combine all features
        combined_features = pd.concat(all_features, ignore_index=True)
        
        logger.info(f"Loaded {len(combined_features)} total samples")
        logger.info(f"Label distribution: {pd.Series(all_labels).value_counts().to_dict()}")
        
        # Train model
        results = self.trainer.train(
            combined_features, all_labels,
            validate=validate,
            tune_hyperparameters=tune_hyperparameters
        )
        
        # Save model
        model_filename = f"{self.trainer.model_type}_model_{int(time.time())}.joblib"
        model_path = self.models_dir / model_filename
        self.trainer.save_model(str(model_path))
        results["model_path"] = str(model_path)
        
        # Plot results if validation was performed
        if validate and "confusion_matrix" in results:
            plot_path = self.models_dir / f"{self.trainer.model_type}_training_results_{int(time.time())}.png"
            self.trainer.plot_training_results(results, str(plot_path))
        
        return results
    
    def evaluate_model(self, model_path: str, test_data_files: List[str],
                      label_column: str = "label") -> Dict[str, Any]:
        """
        Evaluate a trained model on test data.
        
        Args:
            model_path: Path to saved model
            test_data_files: List of test data files
            label_column: Name of label column
            
        Returns:
            Evaluation results
        """
        # Load model
        self.trainer.load_model(model_path)
        
        # Load test data
        test_features = []
        test_labels = []
        
        for data_file in test_data_files:
            df = pd.read_csv(data_file)
            features = df.drop(columns=[label_column])
            labels = df[label_column].tolist()
            
            test_features.append(features)
            test_labels.extend(labels)
        
        combined_test_features = pd.concat(test_features, ignore_index=True)
        
        # Make predictions
        predicted_labels, prediction_probs = self.trainer.predict(combined_test_features)
        
        # Calculate metrics
        from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
        
        accuracy = accuracy_score(test_labels, predicted_labels)
        class_report = classification_report(test_labels, predicted_labels, output_dict=True)
        cm = confusion_matrix(test_labels, predicted_labels)
        
        results = {
            "accuracy": accuracy,
            "classification_report": class_report,
            "confusion_matrix": cm.tolist(),
            "predictions": predicted_labels,
            "probabilities": prediction_probs.tolist(),
            "true_labels": test_labels
        }
        
        logger.info(f"Test accuracy: {accuracy:.3f}")
        
        return results


def main():
    """Test the ML module."""
    # Example configuration
    config = {
        "type": "random_forest",
        "random_forest": {
            "n_estimators": 50,
            "max_depth": 10,
            "random_state": 42
        },
        "training": {
            "test_size": 0.2,
            "validation_size": 0.1,
            "cross_validation_folds": 3
        },
        "models_dir": "models"
    }
    
    # Create sample data for testing
    np.random.seed(42)
    n_samples = 200
    
    # Simulate WiFi features for different presence states
    features_data = []
    labels_data = []
    
    for state in ["visible_camera", "behind_wall", "left_area"]:
        for _ in range(n_samples // 3):
            if state == "visible_camera":
                # High signal strength, low volatility
                rssi_mean = -45 + np.random.normal(0, 5)
                rssi_volatility = 0.5 + np.random.exponential(0.3)
                time_since_last = 0
            elif state == "behind_wall":
                # Medium signal strength, high volatility
                rssi_mean = -60 + np.random.normal(0, 8)
                rssi_volatility = 2.0 + np.random.exponential(1)
                time_since_last = np.random.uniform(1, 10)
            else:  # left_area
                # Low signal strength, low volatility
                rssi_mean = -75 + np.random.normal(0, 10)
                rssi_volatility = 0.3 + np.random.exponential(0.2)
                time_since_last = np.random.uniform(10, 30)
            
            features = {
                "rssi_mean": rssi_mean,
                "rssi_std": np.abs(np.random.normal(3, 1)),
                "rssi_volatility": rssi_volatility,
                "rssi_range": np.abs(np.random.normal(5, 2)),
                "time_since_last_person": time_since_last,
                "was_recently_visible": 1 if time_since_last < 5 else 0
            }
            
            features_data.append(features)
            labels_data.append(state)
    
    # Create DataFrame
    features_df = pd.DataFrame(features_data)
    
    print("Created sample dataset:")
    print(f"Features shape: {features_df.shape}")
    print(f"Label distribution: {pd.Series(labels_data).value_counts()}")
    
    # Initialize and train model
    pipeline = MLPipeline(config)
    
    results = pipeline.trainer.train(
        features_df, labels_data,
        validate=True,
        tune_hyperparameters=False
    )
    
    print(f"\nTraining Results:")
    print(f"Test Accuracy: {results.get('test_accuracy', 0):.3f}")
    print(f"CV Accuracy: {results.get('cv_mean', 0):.3f} ± {results.get('cv_std', 0):.3f}")
    
    # Test prediction on new data
    test_features = pd.DataFrame([{
        "rssi_mean": -65,
        "rssi_std": 3,
        "rssi_volatility": 1.5,
        "rssi_range": 8,
        "time_since_last_person": 3,
        "was_recently_visible": 1
    }])
    
    predictions, probabilities = pipeline.trainer.predict(test_features)
    print(f"\nTest Prediction: {predictions[0]}")
    print(f"Probabilities: {probabilities[0]}")


if __name__ == "__main__":
    main()