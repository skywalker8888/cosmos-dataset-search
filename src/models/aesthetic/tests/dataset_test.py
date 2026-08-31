# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Unit tests for dataloader for aesthetic predictor."""

from pathlib import Path

import numpy as np
import pytest
import pytorch_lightning as pl
import torch
import webdataset as wds

from src.models.aesthetic import AestheticPredictor, make_loader

# Requires CUDA: the Lightning Trainer below is constructed with
# accelerator="gpu" and devices=torch.cuda.device_count(), which is 0 on a
# CPU-only host. Deselect with -m "not gpu".
pytestmark = pytest.mark.gpu

EMBEDDING_SIZE: int = 128
BATCH_SIZE: int = 10


def test_make_loader(tmp_path: Path) -> None:
    """Test dataloader for aesthetic embeddings dataset."""

    url = (tmp_path / "shard-%06d.tar").as_posix()
    with wds.ShardWriter(url, maxcount=100) as sink:
        for i in range(1000):
            sink.write(
                {
                    "__key__": str(i),
                    "embedding.pyd": np.random.rand(1, EMBEDDING_SIZE).astype(
                        np.float32
                    ),
                    "aesthetic_score.pyd": np.random.rand() * 10.0,
                }
            )

    train_loader = make_loader(
        (tmp_path / "shard-{000001..000007}.tar").as_posix(),
        mode="train",
        batch_size=BATCH_SIZE,
        num_workers=2,
        shuffle_buffer=2,
    )

    val_loader = make_loader(
        (tmp_path / "shard-{000008..000009}.tar").as_posix(),
        mode="val",
        batch_size=BATCH_SIZE,
        num_workers=2,
        shuffle_buffer=2,
    )

    for i, (embeddings, scores) in enumerate(train_loader):
        break

    assert isinstance(embeddings, torch.Tensor)
    assert isinstance(scores, torch.Tensor)
    assert embeddings.shape == (BATCH_SIZE, EMBEDDING_SIZE)
    assert scores.shape == (BATCH_SIZE, 1)

    # test training and validation dataloaders
    model = AestheticPredictor(EMBEDDING_SIZE)
    trainer = pl.Trainer(
        devices=torch.cuda.device_count(),
        accelerator="gpu",
        strategy="ddp",
        max_steps=5,
    )
    trainer.fit(model, train_dataloaders=train_loader, val_dataloaders=val_loader)
