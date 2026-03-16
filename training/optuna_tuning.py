"""
Hyperparameter optimization via Optuna.

Uses TPE sampler with pruning for efficient search.
Separate tuning functions for LightGBM (regime classifier)
and PyTorch SignalModel.
"""

from typing import Optional

import numpy as np
import optuna
import pandas as pd
import structlog

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = structlog.get_logger()


def tune_regime_classifier(
    X: pd.DataFrame,
    y: pd.Series,
    n_trials: int = 50,
    cv_folds: int = 3,
    random_state: int = 42,
) -> dict:
    """
    Tune LightGBM regime classifier hyperparameters via Optuna.

    Uses time-series-aware cross-validation (no random shuffle).
    Metric: macro-F1 on out-of-sample fold.

    Args:
        X: Feature DataFrame
        y: Regime labels {0, 1, 2}
        n_trials: Number of Optuna trials
        cv_folds: Number of CV folds (simple sequential split)
        random_state: Seed for reproducibility

    Returns:
        dict of best LightGBM hyperparameters
    """
    import lightgbm as lgb
    from sklearn.metrics import f1_score
    from sklearn.model_selection import TimeSeriesSplit

    tscv = TimeSeriesSplit(n_splits=cv_folds)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=100),
            "num_leaves": trial.suggest_categorical("num_leaves", [31, 63, 127]),
            "learning_rate": trial.suggest_categorical("learning_rate", [0.01, 0.05, 0.1]),
            "max_depth": trial.suggest_categorical("max_depth", [4, 6, 8]),
            "min_child_samples": trial.suggest_categorical("min_child_samples", [20, 50, 100]),
            "subsample": trial.suggest_categorical("subsample", [0.7, 0.8, 1.0]),
            "colsample_bytree": trial.suggest_categorical("colsample_bytree", [0.7, 0.8, 1.0]),
            "class_weight": "balanced",
            "objective": "multiclass",
            "num_class": 3,
            "metric": "multi_logloss",
            "device": "cpu",
            "verbose": -1,
            "random_state": random_state,
        }

        fold_scores = []
        for train_idx, val_idx in tscv.split(X):
            X_tr, X_vl = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_vl = y.iloc[train_idx], y.iloc[val_idx]

            model = lgb.LGBMClassifier(**params)
            model.fit(X_tr, y_tr)
            preds = model.predict(X_vl)
            score = f1_score(y_vl, preds, average="macro")
            fold_scores.append(score)

        return float(np.mean(fold_scores))

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=random_state),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = study.best_params
    best_params.update({
        "class_weight": "balanced",
        "objective": "multiclass",
        "num_class": 3,
        "metric": "multi_logloss",
        "device": "cpu",
        "verbose": -1,
        "random_state": random_state,
    })

    logger.info(
        f"RegimeClassifier tuning complete: best F1={study.best_value:.4f}",
        params=best_params,
    )
    return best_params


def tune_signal_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    n_trials: int = 30,
    random_state: int = 42,
    device: str = None,
) -> dict:
    """
    Tune SignalModel hyperparameters via Optuna.

    Metric: validation accuracy (proxy for Sharpe — fast to compute during tuning).
    Full walk-forward Sharpe validation is done after tuning with best params.

    Args:
        X_train: Scaled training features
        y_train: Training labels {-1, 0, +1}
        X_val: Scaled validation features
        y_val: Validation labels
        n_trials: Number of Optuna trials
        random_state: Seed
        device: 'cuda' or 'cpu' (auto-detect if None)

    Returns:
        dict of best SignalModel constructor kwargs + training config
    """
    import torch
    from models.signal_model import SignalModel
    from training.trainer import SignalModelTrainer

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    def objective(trial: optuna.Trial) -> float:
        # Architecture hyperparams
        channels_choice = trial.suggest_categorical(
            "tcn_channels", ["32_64_128", "16_32_64", "64_128_256"]
        )
        channel_map = {
            "32_64_128": [32, 64, 128],
            "16_32_64": [16, 32, 64],
            "64_128_256": [64, 128, 256],
        }
        tcn_channels = channel_map[channels_choice]

        model_kwargs = {
            "tcn_channels": tcn_channels,
            "tcn_kernel_size": trial.suggest_categorical("tcn_kernel_size", [3, 5]),
            "tcn_dropout": trial.suggest_float("tcn_dropout", 0.1, 0.4, step=0.1),
            "attention_heads": trial.suggest_categorical("attention_heads", [4, 8]),
            "dropout": trial.suggest_float("dropout", 0.2, 0.5, step=0.1),
        }

        training_config = {
            "learning_rate": trial.suggest_float("learning_rate", 1e-4, 1e-2, log=True),
            "weight_decay": trial.suggest_float("weight_decay", 1e-5, 1e-3, log=True),
            "epochs": 30,  # Short for tuning
            "early_stopping_patience": 8,
            "batch_size": trial.suggest_categorical("batch_size", [128, 256, 512]),
        }

        model = SignalModel(**model_kwargs)
        trainer = SignalModelTrainer(
            model=model,
            device=device,
            use_amp=True,
            use_compile=False,  # Disable compile during tuning (overhead)
        )

        history = trainer.fit(
            X_train, y_train, X_val, y_val,
            config=training_config,
            checkpoint_path=f"/tmp/optuna_trial_{trial.number}.pt",
        )

        # Use best validation accuracy as metric
        best_val_acc = max(history.get("val_acc", [0.0]))
        return best_val_acc

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=random_state),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=10),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_params
    channel_map = {
        "32_64_128": [32, 64, 128],
        "16_32_64": [16, 32, 64],
        "64_128_256": [64, 128, 256],
    }
    best_model_kwargs = {
        "tcn_channels": channel_map[best["tcn_channels"]],
        "tcn_kernel_size": best["tcn_kernel_size"],
        "tcn_dropout": best["tcn_dropout"],
        "attention_heads": best["attention_heads"],
        "dropout": best["dropout"],
    }
    best_training_config = {
        "learning_rate": best["learning_rate"],
        "weight_decay": best["weight_decay"],
        "batch_size": best["batch_size"],
        "epochs": 100,  # Full training after tuning
        "early_stopping_patience": 15,
    }

    logger.info(
        f"SignalModel tuning complete: best val_acc={study.best_value:.4f}",
        model_kwargs=best_model_kwargs,
    )
    return {"model_kwargs": best_model_kwargs, "training_config": best_training_config}
