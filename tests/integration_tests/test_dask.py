from contextlib import contextmanager
import tempfile
from typing import Iterator

from distributed import Client
from distributed import Scheduler
from distributed import Worker
from distributed.utils_test import gen_cluster
import joblib
import numpy as np
import pytest

import optuna
from optuna.integration.dask import _OptunaSchedulerExtension
from optuna.integration.dask import DaskStorage
from optuna.trial import Trial


STORAGE_MODES = ["inmemory", "sqlite"]


@contextmanager
def get_storage_url(specifier: str) -> Iterator:
    tmpfile = None
    try:
        if specifier == "inmemory":
            url = None
        elif specifier == "sqlite":
            tmpfile = tempfile.NamedTemporaryFile()
            url = "sqlite:///{}".format(tmpfile.name)
        else:
            raise ValueError(
                "Invalid specifier entered. Was expecting 'inmemory' or 'sqlite'"
                f"but got {specifier} instead"
            )
        yield url
    finally:
        if tmpfile is not None:
            tmpfile.close()


def objective(trial: Trial) -> float:
    x = trial.suggest_uniform("x", -10, 10)
    return (x - 2) ** 2


@gen_cluster(client=True)
async def test_experimental(c: Client, s: Scheduler, a: Worker, b: Worker) -> None:
    with pytest.warns(optuna._experimental.ExperimentalWarning):
        DaskStorage()


@gen_cluster(client=True)
async def test_daskstorage_registers_extension(
    c: Client, s: Scheduler, a: Worker, b: Worker
) -> None:
    assert "optuna" not in s.extensions
    await DaskStorage()
    assert "optuna" in s.extensions
    assert isinstance(s.extensions["optuna"], _OptunaSchedulerExtension)


@gen_cluster(client=True)
async def test_name(c: Client, s: Scheduler, a: Worker, b: Worker) -> None:
    await DaskStorage(name="foo")
    ext = s.extensions["optuna"]
    assert len(ext.storages) == 1
    assert isinstance(ext.storages["foo"], optuna.storages.InMemoryStorage)

    await DaskStorage(name="bar")
    assert len(ext.storages) == 2
    assert isinstance(ext.storages["bar"], optuna.storages.InMemoryStorage)


@gen_cluster(client=True)
async def test_name_unique(c: Client, s: Scheduler, a: Worker, b: Worker) -> None:
    s1 = await DaskStorage()
    s2 = await DaskStorage()
    assert s1.name != s2.name


@pytest.mark.parametrize("storage_specifier", STORAGE_MODES)
@pytest.mark.parametrize("processes", [True, False])
def test_optuna_joblib_backend(storage_specifier: str, processes: bool) -> None:
    with Client(processes=processes):
        with get_storage_url(storage_specifier) as url:
            storage = DaskStorage(url)
            study = optuna.create_study(storage=storage)
            with joblib.parallel_backend("dask"):
                study.optimize(objective, n_trials=10, n_jobs=-1)
            assert len(study.trials) == 10


@pytest.mark.parametrize("storage_specifier", STORAGE_MODES)
def test_get_base_storage(storage_specifier: str) -> None:
    with Client():
        with get_storage_url(storage_specifier) as url:
            dask_storage = DaskStorage(url)
            storage = dask_storage.get_base_storage()
            expected_type = type(optuna.storages.get_storage(url))
            assert isinstance(storage, expected_type)


@pytest.mark.parametrize("processes", [True, False])
@pytest.mark.parametrize("direction", ["maximize", "minimize"])
def test_study_direction_best_value(processes: bool, direction: str) -> None:
    # Regression test for https://github.com/jrbourbeau/dask-optuna/issues/15
    pytest.importorskip("pandas")
    with Client(processes=processes):
        dask_storage = DaskStorage()
        study = optuna.create_study(storage=dask_storage, direction=direction)
        with joblib.parallel_backend("dask"):
            study.optimize(objective, n_trials=10, n_jobs=-1)

        # Ensure that study.best_value matches up with the expected value from
        # the trials DataFrame
        trials_value = study.trials_dataframe()["value"]
        if direction == "maximize":
            expected = trials_value.max()
        else:
            expected = trials_value.min()

        np.testing.assert_allclose(expected, study.best_value)
