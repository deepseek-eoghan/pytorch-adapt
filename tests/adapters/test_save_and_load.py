import os
import shutil
import unittest

import numpy as np
import torch

from pytorch_adapt.containers.base_container import containers_are_equal
from pytorch_adapt.utils import common_functions as c_f
from pytorch_adapt.utils import exceptions, savers
from pytorch_adapt.validators import AccuracyValidator, MultipleValidators

from .. import TEST_DEVICE, TEST_FOLDER
from .get_dann import get_dann


def get_stat_getter():
    return MultipleValidators(
        [
            AccuracyValidator(key_map={"src_train": "src_val"}),
            AccuracyValidator(),
        ]
    )


def get_validator():
    return MultipleValidators(
        [
            AccuracyValidator(),
            AccuracyValidator(),
        ]
    )


class TestSaveAndLoad(unittest.TestCase):
    def test_save_and_load(self):
        max_epochs = 3
        saver = savers.Saver(folder=TEST_FOLDER)

        stat_getter1 = get_stat_getter()
        validator1 = get_validator()

        dann1, datasets = get_dann()
        dann1.run(
            datasets=datasets,
            epoch_length=2,
            validator=validator1,
            stat_getter=stat_getter1,
            saver=saver,
            max_epochs=max_epochs,
        )

        for load_all_at_once in [True, False]:
            stat_getter2 = get_stat_getter()
            validator2 = get_validator()
            dann2, _ = get_dann()
            dann2.dist_init()

            self.assert_not_equal(
                dann1, validator1, stat_getter1, dann2, validator2, stat_getter2
            )

            if load_all_at_once:
                saver.load_all(dann2.adapter, validator2, stat_getter2, dann2)
            else:
                saver.load_ignite(dann2.trainer)
                saver.load_adapter(dann2.adapter, max_epochs)
                saver.load_stat_getter(stat_getter2)
                saver.load_validator(validator2)

            self.assert_equal(
                dann1, validator1, stat_getter1, dann2, validator2, stat_getter2
            )

        dann3, _ = get_dann()
        dann3.dist_init()
        stat_getter3 = get_stat_getter()
        validator3 = get_validator()
        self.assert_not_equal(
            dann1, validator1, stat_getter1, dann3, validator3, stat_getter3
        )
        saver = savers.Saver(folder=TEST_FOLDER)
        # this should load and then not run
        # because it has already run for max_epochs
        dann3.run(
            datasets=datasets,
            epoch_length=2,
            validator=validator3,
            stat_getter=stat_getter3,
            saver=saver,
            max_epochs=max_epochs,
            resume="latest",
        )
        self.assert_equal(
            dann1, validator1, stat_getter1, dann3, validator3, stat_getter3
        )

        validator3.epochs = validator3.epochs[:1]
        validator3.score_history = validator3.score_history[:1]
        saver.save_validator(validator3)
        with self.assertRaises(exceptions.ResumeCheckError):
            dann3.run(
                datasets=datasets,
                epoch_length=2,
                validator=validator3,
                stat_getter=stat_getter3,
                saver=saver,
                max_epochs=max_epochs,
                resume="latest",
            )

        validator3 = MultipleValidators(
            [
                AccuracyValidator(),
                AccuracyValidator(),
                AccuracyValidator(),
            ]
        )

        validator4 = AccuracyValidator()

        self.assertRaises(FileNotFoundError, lambda: saver.load_validator(validator3))
        self.assertRaises(FileNotFoundError, lambda: saver.load_validator(validator4))

        shutil.rmtree(TEST_FOLDER)

    def assert_not_equal(
        self, dann1, validator1, stat_getter1, dann2, validator2, stat_getter2
    ):
        # check ignite engine state
        self.assertTrue(dann1.trainer.state_dict() != dann2.trainer.state_dict())

        # check adapter.containers
        self.assertTrue(
            not containers_are_equal(dann1.adapter.containers, dann2.adapter.containers)
        )

        # check the attributes as well
        for k in ["models"]:
            c1 = getattr(dann1.adapter, k)
            c2 = getattr(dann2.adapter, k)
            self.assertTrue(not containers_are_equal(c1, c2))

        for attrname in ["best_epoch", "best_score", "latest_score"]:
            self.assertTrue(getattr(stat_getter2, attrname) is None)
            self.assertTrue(getattr(validator2, attrname) is None)

    def assert_equal(
        self, dann1, validator1, stat_getter1, dann2, validator2, stat_getter2
    ):
        self.assertTrue(dann1.trainer.state_dict() == dann2.trainer.state_dict())

        # check adapter.containers
        self.assertTrue(
            containers_are_equal(dann1.adapter.containers, dann2.adapter.containers)
        )

        # check the attributes as well
        for k in [
            "models",
            "optimizers",
            "lr_schedulers",
            "misc",
        ]:
            c1 = getattr(dann1.adapter, k)
            c2 = getattr(dann2.adapter, k)
            self.assertTrue(containers_are_equal(c1, c2))

        for attrname in ["best_epoch", "best_score", "latest_score"]:
            self.assertTrue(
                getattr(stat_getter1, attrname) == getattr(stat_getter2, attrname)
            )
            self.assertTrue(
                getattr(validator1, attrname) == getattr(validator2, attrname)
            )

        for attrname in ["score_history", "epochs"]:
            self.assertTrue(
                np.array_equal(
                    getattr(stat_getter1, attrname), getattr(stat_getter2, attrname)
                )
            )
            self.assertTrue(
                np.array_equal(
                    getattr(validator1, attrname), getattr(validator2, attrname)
                )
            )