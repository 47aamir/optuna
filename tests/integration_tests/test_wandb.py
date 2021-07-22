from unittest import mock

import optuna
from optuna.integration import WeightsAndBiasesCallback


def _objective_func(trial: optuna.trial.Trial) -> float:

    x = trial.suggest_uniform("x", low=-10, high=10)
    y = trial.suggest_loguniform("y", low=1, high=10)
    return (x - 2) ** 2 + (y - 25) ** 2


@mock.patch("optuna.integration.wandb.wandb")
def test_run_initialized(wandb: mock.MagicMock) -> None:

    wandb_kwargs = {
        "project": "optuna",
        "group": "summary",
        "job_type": "logging",
        "mode": "offline",
    }

    WeightsAndBiasesCallback(
        metric_name="mse",
        wandb_kwargs=wandb_kwargs,
    )

    wandb.init.assert_called_once_with(
        project="optuna",
        group="summary",
        job_type="logging",
        mode="offline",
    )


@mock.patch("optuna.integration.wandb.wandb")
def test_attributes_set_on_epoch(wandb: mock.MagicMock) -> None:

    wandb.config.update = mock.MagicMock()

    wandbc = WeightsAndBiasesCallback()
    study = optuna.create_study(direction="minimize")
    study.optimize(_objective_func, n_trials=1, callbacks=[wandbc])

    expected = {"direction": "MINIMIZE"}
    wandb.config.update.assert_called_once_with(expected)


@mock.patch("optuna.integration.wandb.wandb")
def test_log_api_call_count(wandb: mock.Mock) -> None:

    wandb.log = mock.MagicMock()

    wandbc = WeightsAndBiasesCallback()
    target_n_trials = 10
    study = optuna.create_study()
    study.optimize(_objective_func, n_trials=target_n_trials, callbacks=[wandbc])
    assert wandb.log.call_count == target_n_trials


@mock.patch("optuna.integration.wandb.wandb")
def test_values_registered_on_epoch(wandb: mock.Mock) -> None:

    wandb.log = mock.MagicMock()

    wandbc = WeightsAndBiasesCallback()
    study = optuna.create_study()
    study.optimize(_objective_func, n_trials=1, callbacks=[wandbc])

    kall = wandb.log.call_args
    assert list(kall[0][0].keys()) == ["x", "y", "value"]
    assert kall[1] == {"step": 0}
