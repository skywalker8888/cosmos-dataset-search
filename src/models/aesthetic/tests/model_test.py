# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Unit tests for aesthetic predictor model."""

from typing import Tuple

import numpy as np
import pytest
import pytorch_lightning as pl
import torch
from torch import nn

from src.models.aesthetic import AestheticPredictor, load_model

INPUT_SIZE = 16


@pytest.fixture
def model() -> AestheticPredictor:
    """Model fixture."""
    return AestheticPredictor(INPUT_SIZE)


def test_aesthetic_predictor_forward(model: AestheticPredictor) -> None:
    """Aesthetic predictor model forward function."""

    x = torch.rand(size=(4, INPUT_SIZE), dtype=torch.float32)
    with torch.no_grad():
        y, _, _ = model(x)
    assert y.shape == (4, 1)
    assert np.all(np.isfinite(y.cpu().numpy()))


def test_aesthetic_predictor_train(model: AestheticPredictor) -> None:
    """Aesthetic predictor model train function."""

    train_batches = torch.utils.data.TensorDataset(
        torch.rand(size=(4, INPUT_SIZE), dtype=torch.float32),
        torch.rand(size=(4, 1), dtype=torch.float32),
    )
    train_dataloader = torch.utils.data.DataLoader(train_batches, batch_size=2)

    val_batches = torch.utils.data.TensorDataset(
        torch.rand(size=(4, INPUT_SIZE), dtype=torch.float32),
        torch.rand(size=(4, 1), dtype=torch.float32),
    )
    val_dataloader = torch.utils.data.DataLoader(val_batches, batch_size=2)

    trainer = pl.Trainer(max_epochs=1)
    trainer.fit(model, train_dataloader, val_dataloader)


# Requires pretrained weights under models/aesthetic/variants/*.pth, which are
# not committed to this repository. Without them this test fails with
# FileNotFoundError. Deselect with -m "not integration".
@pytest.mark.integration
@pytest.mark.parametrize(
    "params",
    [
        ("ViT-L-14", "openai", False),
        ("ViT-H-14", "laion2b_s32b_b79k", False),
        ("ViT-L-14", "datacomp_xl_s13b_b90k", False),
    ],
)
def test_load_model(params: Tuple[str, str, bool]) -> None:
    """Test loading pre-trained models."""

    model = load_model(*params)
    assert isinstance(model, nn.Module)


def test_load_model_incorrect() -> None:
    """Test loading incorrect models."""

    with pytest.raises(KeyError):
        load_model("ViT-L-14", "incorrect_key")

    with pytest.raises(NotImplementedError):
        load_model("ViT-G-14", "openai")
