"""
TCN Multi-Branch Signal Model (Level 2).

4-branch architecture:
    Branch A: Temporal sequence (TCN) — 20 bars × 8 features
    Branch B: Order flow snapshot (MLP) — 7 features
    Branch C: Volatility context (MLP) — 6 features
    Branch D: News context (MLP) — 5 features
    Fusion: Attention-weighted concat → 3-class output

Output: LogSoftmax over [P_short, P_skip, P_long]
    class 0 → label -1 (Short)
    class 1 → label  0 (Skip)
    class 2 → label +1 (Long)

Optimized for RTX 5070: supports torch.compile() and BF16 autocast.
"""

from pathlib import Path
from typing import Dict, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
import structlog

from models.tcn import TCN

logger = structlog.get_logger()

# Label → class index mapping
LABEL_TO_CLASS = {-1: 0, 0: 1, 1: 2}
CLASS_TO_LABEL = {0: -1, 1: 0, 2: 1}


class SignalModel(nn.Module):
    """
    Multi-branch fusion model for trading signal prediction.

    All branches are independently encoded, then concatenated and processed
    through a multi-head attention layer before the final classification head.

    Architecture summary:
        Branch A (TCN):   [B, 20, 8]  → [B, 128]
        Branch B (MLP):   [B, 7]      → [B, 64]
        Branch C (MLP):   [B, 6]      → [B, 32]
        Branch D (MLP):   [B, 5]      → [B, 16]
        Concat:                          [B, 240]
        Attention:        [B, 1, 240] → [B, 240]
        Head:             [B, 240]    → [B, 3]

    Args:
        tcn_channels: TCN layer channels (default [32, 64, 128])
        tcn_kernel_size: TCN kernel size
        tcn_dropout: TCN dropout rate
        attention_heads: Number of attention heads
        dropout: Classification head dropout
        seq_len: Temporal sequence length (default 20 bars)
        n_temporal_features: Features in Branch A (default 8)
        n_orderflow_features: Features in Branch B (default 7)
        n_volatility_features: Features in Branch C (default 6)
        n_news_features: Features in Branch D (default 5)
    """

    def __init__(
        self,
        tcn_channels: list = None,
        tcn_kernel_size: int = 3,
        tcn_dropout: float = 0.2,
        attention_heads: int = 4,
        dropout: float = 0.3,
        seq_len: int = 20,
        n_temporal_features: int = 8,
        n_orderflow_features: int = 7,
        n_volatility_features: int = 6,
        n_news_features: int = 5,
    ):
        super().__init__()
        if tcn_channels is None:
            tcn_channels = [32, 64, 128]

        self.seq_len = seq_len

        # ---- Branch A: Temporal (TCN) ----
        self.temporal_encoder = TCN(
            n_inputs=n_temporal_features,
            channels=tcn_channels,
            kernel_size=tcn_kernel_size,
            dropout=tcn_dropout,
        )
        branch_a_dim = tcn_channels[-1]  # 128

        # ---- Branch B: Order Flow (MLP) ----
        self.orderflow_encoder = nn.Sequential(
            nn.Linear(n_orderflow_features, 32),
            nn.LayerNorm(32),
            nn.ReLU(),
            nn.Linear(32, 64),
            nn.ReLU(),
        )
        branch_b_dim = 64

        # ---- Branch C: Volatility (MLP) ----
        self.volatility_encoder = nn.Sequential(
            nn.Linear(n_volatility_features, 32),
            nn.LayerNorm(32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 32),
        )
        branch_c_dim = 32

        # ---- Branch D: News (MLP) ----
        self.news_encoder = nn.Sequential(
            nn.Linear(n_news_features, 16),
            nn.ReLU(),
            nn.Linear(16, 16),
        )
        branch_d_dim = 16

        # ---- Fusion ----
        self.fusion_dim = branch_a_dim + branch_b_dim + branch_c_dim + branch_d_dim  # 240

        self.attention = nn.MultiheadAttention(
            embed_dim=self.fusion_dim,
            num_heads=attention_heads,
            dropout=0.1,
            batch_first=True,
        )
        self.attention_norm = nn.LayerNorm(self.fusion_dim)

        # ---- Classification Head ----
        self.head = nn.Sequential(
            nn.Linear(self.fusion_dim, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 3),
        )

        self._init_weights()

    def _init_weights(self):
        """Xavier uniform init for linear layers."""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(
        self,
        temporal: torch.Tensor,
        orderflow: torch.Tensor,
        volatility: torch.Tensor,
        news: torch.Tensor,
    ) -> torch.Tensor:
        """
        Forward pass through all branches, fusion, and classification head.

        Args:
            temporal:   [batch, seq_len, n_temporal_features]
            orderflow:  [batch, n_orderflow_features]
            volatility: [batch, n_volatility_features]
            news:       [batch, n_news_features]

        Returns:
            [batch, 3] — log-probabilities via LogSoftmax
        """
        # Encode each branch
        a = self.temporal_encoder(temporal)           # [B, 128]
        b = self.orderflow_encoder(orderflow)         # [B, 64]
        c = self.volatility_encoder(volatility)       # [B, 32]
        d = self.news_encoder(news)                   # [B, 16]

        # Concat
        fused = torch.cat([a, b, c, d], dim=-1)       # [B, 240]

        # Self-attention over the fused vector (treat as single-token sequence)
        fused_3d = fused.unsqueeze(1)                 # [B, 1, 240]
        attn_out, _ = self.attention(fused_3d, fused_3d, fused_3d)
        fused = self.attention_norm(attn_out.squeeze(1) + fused)  # [B, 240] + residual

        # Classification
        logits = self.head(fused)                     # [B, 3]
        return F.log_softmax(logits, dim=-1)

    def predict(self, features_dict: Dict[str, torch.Tensor]) -> tuple:
        """
        Single-sample or batch inference returning signal and confidence.

        Args:
            features_dict: dict with keys 'temporal', 'orderflow', 'volatility', 'news'

        Returns:
            Tuple of (signal: int {-1, 0, +1}, confidence: float [0, 1])
            For batch input: returns lists.
        """
        self.eval()
        with torch.no_grad():
            log_probs = self.forward(
                features_dict["temporal"],
                features_dict["orderflow"],
                features_dict["volatility"],
                features_dict["news"],
            )
            probs = torch.exp(log_probs)

            if probs.dim() == 1:
                # Single sample
                class_idx = int(probs.argmax().item())
                confidence = float(probs[class_idx].item())
                return CLASS_TO_LABEL[class_idx], confidence
            else:
                # Batch
                class_indices = probs.argmax(dim=-1).tolist()
                confidences = probs.max(dim=-1).values.tolist()
                signals = [CLASS_TO_LABEL[c] for c in class_indices]
                return signals, confidences

    def save(self, path: str) -> None:
        """Save model state dict to path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.state_dict(),
                "config": {
                    "fusion_dim": self.fusion_dim,
                    "seq_len": self.seq_len,
                },
            },
            path,
        )
        logger.info(f"SignalModel saved to {path}")

    @classmethod
    def load(cls, path: str, device: str = "cpu", **model_kwargs) -> "SignalModel":
        """Load model from saved checkpoint."""
        checkpoint = torch.load(path, map_location=device)
        model = cls(**model_kwargs)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        logger.info(f"SignalModel loaded from {path}")
        return model
