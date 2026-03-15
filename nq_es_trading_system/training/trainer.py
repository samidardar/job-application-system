"""
PyTorch training loop for the SignalModel.

RTX 5070 (Blackwell) optimizations:
    - BF16 autocast via torch.amp.autocast(dtype=torch.bfloat16)
    - torch.compile(model, mode='max-autotune') for ~20% speedup
    - pin_memory=True + num_workers=4 for fast DataLoader
    - Gradient clipping (max_norm=1.0) for stability
"""

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
import structlog

from models.signal_model import SignalModel, LABEL_TO_CLASS

logger = structlog.get_logger()


def _make_tensors(
    X_temporal: np.ndarray,
    X_orderflow: np.ndarray,
    X_volatility: np.ndarray,
    X_news: np.ndarray,
    y: np.ndarray,
) -> TensorDataset:
    """Convert numpy arrays to a TensorDataset."""
    return TensorDataset(
        torch.tensor(X_temporal, dtype=torch.float32),
        torch.tensor(X_orderflow, dtype=torch.float32),
        torch.tensor(X_volatility, dtype=torch.float32),
        torch.tensor(X_news, dtype=torch.float32),
        torch.tensor(y, dtype=torch.long),
    )


def prepare_sequences(
    X: pd.DataFrame,
    y: pd.Series,
    seq_len: int = 20,
    temporal_cols: list = None,
    orderflow_cols: list = None,
    volatility_cols: list = None,
    news_cols: list = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Convert flat feature DataFrame into branch-specific tensors.

    Creates rolling windows of length seq_len for the temporal (TCN) branch.
    Other branches use only the current bar's features (no window).

    Args:
        X: Scaled feature DataFrame (rows = bars)
        y: Label series with values {-1, 0, +1}
        seq_len: Temporal sequence length
        temporal_cols: Columns for Branch A (TCN)
        orderflow_cols: Columns for Branch B
        volatility_cols: Columns for Branch C
        news_cols: Columns for Branch D

    Returns:
        Tuple of (X_temporal, X_orderflow, X_volatility, X_news, y_class)
        Shapes:
            X_temporal:   [N, seq_len, n_temporal]
            X_orderflow:  [N, n_orderflow]
            X_volatility: [N, n_volatility]
            X_news:       [N, n_news]
            y_class:      [N] with class indices {0, 1, 2}
    """
    from features.pipeline import TEMPORAL_FEATURES, ORDERFLOW_FEATURES, VOLATILITY_FEATURES, NEWS_FEATURES

    temporal_cols = temporal_cols or [c for c in TEMPORAL_FEATURES if c in X.columns]
    orderflow_cols = orderflow_cols or [c for c in ORDERFLOW_FEATURES if c in X.columns]
    volatility_cols = volatility_cols or [c for c in VOLATILITY_FEATURES if c in X.columns]
    news_cols = news_cols or [c for c in NEWS_FEATURES if c in X.columns]

    n = len(X) - seq_len
    if n <= 0:
        raise ValueError(f"Not enough data ({len(X)} rows) for seq_len={seq_len}")

    X_temp_arr = X[temporal_cols].values
    X_of_arr = X[orderflow_cols].values
    X_vol_arr = X[volatility_cols].values
    X_news_arr = X[news_cols].values
    y_arr = y.values

    # Build rolling windows for temporal branch
    X_temporal = np.stack([X_temp_arr[i : i + seq_len] for i in range(n)])
    X_orderflow = X_of_arr[seq_len:]
    X_volatility = X_vol_arr[seq_len:]
    X_news = X_news_arr[seq_len:]

    # Convert labels {-1, 0, +1} → class indices {0, 1, 2}
    y_labels = y_arr[seq_len:]
    y_class = np.array([LABEL_TO_CLASS.get(int(lb), 1) for lb in y_labels])

    return X_temporal, X_orderflow, X_volatility, X_news, y_class


class SignalModelTrainer:
    """
    Manages training, validation, and evaluation of SignalModel.

    Supports BF16 autocast and torch.compile for RTX 5070 (Blackwell).
    """

    def __init__(
        self,
        model: SignalModel,
        device: str = None,
        use_amp: bool = True,
        amp_dtype: str = "bfloat16",
        use_compile: bool = True,
        compile_mode: str = "max-autotune",
    ):
        """
        Args:
            model: SignalModel instance
            device: 'cuda', 'cpu', or None (auto-detect)
            use_amp: Enable automatic mixed precision (BF16 for Blackwell)
            amp_dtype: 'bfloat16' (RTX 5070) or 'float16'
            use_compile: Enable torch.compile() (requires PyTorch 2.0+)
            compile_mode: torch.compile mode ('max-autotune' for RTX 5070)
        """
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        self.model = model.to(device)
        self.use_amp = use_amp and device == "cuda"
        self.amp_dtype = torch.bfloat16 if amp_dtype == "bfloat16" else torch.float16

        if use_compile and device == "cuda":
            try:
                self.model = torch.compile(self.model, mode=compile_mode)
                logger.info(f"SignalModelTrainer: torch.compile enabled ({compile_mode})")
            except Exception as e:
                logger.warning(f"SignalModelTrainer: torch.compile failed: {e}")

        logger.info(f"SignalModelTrainer: device={device}, amp={self.use_amp}, dtype={amp_dtype}")

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        config: dict = None,
        class_weights: dict = None,
        checkpoint_path: str = "models/saved/signal_model_best.pt",
        seq_len: int = 20,
    ) -> Dict:
        """
        Full training loop with early stopping.

        Args:
            X_train: Scaled training features
            y_train: Training labels {-1, 0, +1}
            X_val: Scaled validation features
            y_val: Validation labels
            config: Training config dict (lr, epochs, patience, batch_size, ...)
            class_weights: Dict of {class_idx: weight} for CrossEntropyLoss
            checkpoint_path: Path to save best model
            seq_len: Temporal sequence length

        Returns:
            Dict with training history (train_loss, val_loss per epoch)
        """
        cfg = {
            "learning_rate": 1e-3,
            "weight_decay": 1e-4,
            "epochs": 100,
            "early_stopping_patience": 15,
            "batch_size": 256,
            "num_workers": 4,
            "pin_memory": True,
            "grad_clip": 1.0,
        }
        if config:
            cfg.update(config)

        # Build tensors
        train_data = prepare_sequences(X_train, y_train, seq_len=seq_len)
        val_data = prepare_sequences(X_val, y_val, seq_len=seq_len)

        train_loader = DataLoader(
            _make_tensors(*train_data),
            batch_size=cfg["batch_size"],
            shuffle=True,
            num_workers=cfg["num_workers"],
            pin_memory=cfg["pin_memory"] and self.device == "cuda",
            drop_last=True,
        )
        val_loader = DataLoader(
            _make_tensors(*val_data),
            batch_size=cfg["batch_size"] * 2,
            shuffle=False,
            num_workers=cfg["num_workers"],
            pin_memory=cfg["pin_memory"] and self.device == "cuda",
        )

        # Loss with class weights
        if class_weights:
            weight_tensor = torch.tensor(
                [class_weights.get(i, 1.0) for i in range(3)],
                dtype=torch.float32,
            ).to(self.device)
            criterion = nn.NLLLoss(weight=weight_tensor)
        else:
            criterion = nn.NLLLoss()

        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=cfg["learning_rate"],
            weight_decay=cfg["weight_decay"],
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=cfg["epochs"], eta_min=1e-6
        )

        history = {"train_loss": [], "val_loss": [], "val_acc": []}
        best_val_loss = float("inf")
        patience_counter = 0
        checkpoint_path = Path(checkpoint_path)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        for epoch in range(1, cfg["epochs"] + 1):
            train_loss = self.train_epoch(train_loader, optimizer, criterion, cfg["grad_clip"])
            val_loss, val_acc = self.validate_epoch(val_loader, criterion)
            scheduler.step()

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)
            history["val_acc"].append(val_acc)

            if epoch % 10 == 0:
                logger.info(
                    f"Epoch {epoch:3d}/{cfg['epochs']}: "
                    f"train_loss={train_loss:.4f} val_loss={val_loss:.4f} val_acc={val_acc:.3f}"
                )

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                # Save unwrapped model (torch.compile wraps it)
                unwrapped = getattr(self.model, "_orig_mod", self.model)
                unwrapped.save(checkpoint_path)
            else:
                patience_counter += 1
                if patience_counter >= cfg["early_stopping_patience"]:
                    logger.info(f"Early stopping at epoch {epoch} (patience={cfg['early_stopping_patience']})")
                    break

        logger.info(f"Training complete. Best val_loss={best_val_loss:.4f}")
        return history

    def train_epoch(
        self,
        loader: DataLoader,
        optimizer: torch.optim.Optimizer,
        criterion: nn.Module,
        grad_clip: float = 1.0,
    ) -> float:
        """Run one training epoch, return mean loss."""
        self.model.train()
        total_loss = 0.0

        for temporal, orderflow, volatility, news, labels in loader:
            temporal = temporal.to(self.device, non_blocking=True)
            orderflow = orderflow.to(self.device, non_blocking=True)
            volatility = volatility.to(self.device, non_blocking=True)
            news = news.to(self.device, non_blocking=True)
            labels = labels.to(self.device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)

            if self.use_amp:
                with torch.amp.autocast(device_type="cuda", dtype=self.amp_dtype):
                    log_probs = self.model(temporal, orderflow, volatility, news)
                    loss = criterion(log_probs, labels)
            else:
                log_probs = self.model(temporal, orderflow, volatility, news)
                loss = criterion(log_probs, labels)

            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), grad_clip)
            optimizer.step()
            total_loss += loss.item()

        return total_loss / len(loader)

    def validate_epoch(
        self, loader: DataLoader, criterion: nn.Module
    ) -> Tuple[float, float]:
        """Run one validation epoch, return (mean_loss, accuracy)."""
        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0

        with torch.no_grad():
            for temporal, orderflow, volatility, news, labels in loader:
                temporal = temporal.to(self.device, non_blocking=True)
                orderflow = orderflow.to(self.device, non_blocking=True)
                volatility = volatility.to(self.device, non_blocking=True)
                news = news.to(self.device, non_blocking=True)
                labels = labels.to(self.device, non_blocking=True)

                if self.use_amp:
                    with torch.amp.autocast(device_type="cuda", dtype=self.amp_dtype):
                        log_probs = self.model(temporal, orderflow, volatility, news)
                        loss = criterion(log_probs, labels)
                else:
                    log_probs = self.model(temporal, orderflow, volatility, news)
                    loss = criterion(log_probs, labels)

                total_loss += loss.item()
                preds = log_probs.argmax(dim=-1)
                correct += (preds == labels).sum().item()
                total += labels.size(0)

        return total_loss / len(loader), correct / max(total, 1)

    def evaluate(
        self,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        seq_len: int = 20,
        batch_size: int = 512,
    ) -> Dict:
        """
        Full evaluation on test set.

        Returns:
            Dict with accuracy, per-class precision/recall/F1, confusion matrix
        """
        from sklearn.metrics import (
            accuracy_score,
            classification_report,
            confusion_matrix,
        )

        test_data = prepare_sequences(X_test, y_test, seq_len=seq_len)
        loader = DataLoader(
            _make_tensors(*test_data),
            batch_size=batch_size,
            shuffle=False,
            pin_memory=self.device == "cuda",
        )

        all_preds = []
        all_labels = []
        self.model.eval()

        with torch.no_grad():
            for temporal, orderflow, volatility, news, labels in loader:
                temporal = temporal.to(self.device)
                orderflow = orderflow.to(self.device)
                volatility = volatility.to(self.device)
                news = news.to(self.device)

                log_probs = self.model(temporal, orderflow, volatility, news)
                preds = log_probs.argmax(dim=-1).cpu().numpy()
                all_preds.extend(preds.tolist())
                all_labels.extend(labels.numpy().tolist())

        report = classification_report(
            all_labels, all_preds,
            target_names=["short", "skip", "long"],
            output_dict=True,
        )
        cm = confusion_matrix(all_labels, all_preds)

        return {
            "accuracy": accuracy_score(all_labels, all_preds),
            "report": report,
            "confusion_matrix": cm,
        }
