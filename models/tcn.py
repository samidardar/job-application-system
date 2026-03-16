"""
Temporal Convolutional Network (TCN) architecture.

Uses dilated causal convolutions with residual connections.
Optimized for RTX 5070 (Blackwell): supports torch.compile() and BF16.

Reference: Bai et al. "An Empirical Evaluation of Generic Convolutional and
Recurrent Networks for Sequence Modeling" (2018).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class TemporalBlock(nn.Module):
    """
    Single TCN block: dilated causal conv → weight norm → ReLU → dropout.

    Residual connection with 1x1 conv if n_inputs != n_outputs.
    Dilation creates exponentially growing receptive field:
        dilation=1: receptive field = kernel_size
        dilation=2: receptive field = 2 * kernel_size - 1
        ...

    Args:
        n_inputs: Input channels
        n_outputs: Output channels
        kernel_size: Conv kernel size
        stride: Conv stride (always 1 for sequence modeling)
        dilation: Dilation factor
        padding: Zero-padding to maintain sequence length (causal)
        dropout: Dropout rate
    """

    def __init__(
        self,
        n_inputs: int,
        n_outputs: int,
        kernel_size: int,
        stride: int = 1,
        dilation: int = 1,
        padding: int = 0,
        dropout: float = 0.2,
    ):
        super().__init__()

        # Causal padding: pad only the left side so no future information leaks
        self.padding = padding

        self.conv1 = nn.utils.weight_norm(
            nn.Conv1d(
                n_inputs,
                n_outputs,
                kernel_size,
                stride=stride,
                padding=padding,
                dilation=dilation,
            )
        )
        self.chomp1 = _Chomp1d(padding)
        self.relu1 = nn.ReLU()
        self.dropout1 = nn.Dropout(dropout)

        self.conv2 = nn.utils.weight_norm(
            nn.Conv1d(
                n_outputs,
                n_outputs,
                kernel_size,
                stride=stride,
                padding=padding,
                dilation=dilation,
            )
        )
        self.chomp2 = _Chomp1d(padding)
        self.relu2 = nn.ReLU()
        self.dropout2 = nn.Dropout(dropout)

        self.net = nn.Sequential(
            self.conv1,
            self.chomp1,
            self.relu1,
            self.dropout1,
            self.conv2,
            self.chomp2,
            self.relu2,
            self.dropout2,
        )

        # Residual 1x1 conv if channel dimensions differ
        self.downsample = (
            nn.Conv1d(n_inputs, n_outputs, kernel_size=1)
            if n_inputs != n_outputs
            else None
        )
        self.relu = nn.ReLU()
        self._init_weights()

    def _init_weights(self):
        """Kaiming normal init for conv weights."""
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [batch, channels, seq_len]

        Returns:
            [batch, n_outputs, seq_len]
        """
        out = self.net(x)
        res = x if self.downsample is None else self.downsample(x)
        return self.relu(out + res)


class _Chomp1d(nn.Module):
    """Remove right-side padding to maintain causality."""

    def __init__(self, chomp_size: int):
        super().__init__()
        self.chomp_size = chomp_size

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.chomp_size == 0:
            return x
        return x[:, :, : -self.chomp_size].contiguous()


class TCN(nn.Module):
    """
    Temporal Convolutional Network with exponential dilation.

    Architecture:
        Input [batch, seq_len, n_features]
            → transpose to [batch, n_features, seq_len]
            → TemporalBlock(dilation=1)
            → TemporalBlock(dilation=2)
            → TemporalBlock(dilation=4)
            → TemporalBlock(dilation=8)
            → take last timestep → [batch, channels[-1]]

    Total receptive field = sum of (kernel_size - 1) * dilation across all layers * 2.
    With kernel=3, dilations=[1,2,4,8], channels=[32,64,128]:
        RF = 2*(2*1 + 2*2 + 2*4 + 2*8) = 60 timesteps

    Compatible with torch.compile() and BF16 autocast.

    Args:
        n_inputs: Number of input features per timestep (8 for Branch A)
        channels: List of output channels per layer (e.g., [32, 64, 128])
        kernel_size: Kernel size for all conv layers (default 3)
        dropout: Dropout rate (default 0.2)
    """

    def __init__(
        self,
        n_inputs: int,
        channels: list = None,
        kernel_size: int = 3,
        dropout: float = 0.2,
    ):
        super().__init__()
        if channels is None:
            channels = [32, 64, 128]

        layers = []
        num_levels = len(channels)
        in_ch = n_inputs

        for i in range(num_levels):
            dilation = 2 ** i
            out_ch = channels[i]
            padding = (kernel_size - 1) * dilation
            block = TemporalBlock(
                n_inputs=in_ch,
                n_outputs=out_ch,
                kernel_size=kernel_size,
                stride=1,
                dilation=dilation,
                padding=padding,
                dropout=dropout,
            )
            layers.append(block)
            in_ch = out_ch

        self.network = nn.Sequential(*layers)
        self.output_dim = channels[-1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [batch, seq_len, n_features] — note: seq_len first after batch

        Returns:
            [batch, output_dim] — last timestep only
        """
        # TCN expects [batch, channels, seq_len]
        x = x.transpose(1, 2)  # → [batch, n_features, seq_len]
        out = self.network(x)   # → [batch, channels[-1], seq_len]
        return out[:, :, -1]    # → [batch, channels[-1]] last timestep
