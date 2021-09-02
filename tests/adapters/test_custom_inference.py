import os
import shutil
import unittest

import torch

from pytorch_adapt.validators import BaseValidator

from .. import TEST_FOLDER
from .get_dann import get_dann


class TestCustomInference(unittest.TestCase):
    def test_custom_inference(self):
        def custom_inference(cls):
            def func(x, domain):
                features = cls.models["G"](x)
                features = cls.models["C"](features)
                return features, features

            return func

        for use_custom in [False, True]:
            if use_custom:
                dim_size = 10
                inference = custom_inference
            else:
                dim_size = 512
                inference = None

            dann, datasets = get_dann(inference)
            dataset_size = len(datasets["src_val"])

            class CustomAccuracyValidator(BaseValidator):
                def __init__(self, unittester, correct_shape, **kwargs):
                    super().__init__(**kwargs)
                    self.unittester = unittester
                    self.correct_shape = correct_shape

                def compute_score(self, src_val):
                    features = src_val["features"]
                    print("features.shape", features.shape, self.correct_shape)
                    self.unittester.assertTrue(features.shape == self.correct_shape)
                    return 0

            # using default inference method
            dann.run(
                datasets=datasets,
                validator=CustomAccuracyValidator(
                    self, torch.Size([dataset_size, dim_size])
                ),
                epoch_length=1,
                max_epochs=1,
            )

        shutil.rmtree(TEST_FOLDER)