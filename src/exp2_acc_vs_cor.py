import argparse
import json
import random
import time
from datetime import datetime
from itertools import product

import hydra
import matplotlib.pyplot as plt
import numpy as np
import ray
import torch
from dataloader import ARMA
from dataloader import ElectricDevices
from hydra.experimental import compose
from hydra.experimental import initialize
from models.CAE import CAE
from pingouin import distance_corr
from sklearn.metrics import confusion_matrix
from train import Trainer

random.seed(0)  # Not needed
np.random.seed(0)
torch.manual_seed(0)


@ray.remote
def acc_cor(inp, data, cfg, configs):
    exp, seed = inp
    random.seed(seed)  # Seed for the training
    np.random.seed(seed)
    torch.manual_seed(seed)

    tini = time.time()
    print(f"INI exp {exp} seed {seed}. {datetime.now().replace(microsecond=0)}")
    data_train, data_valid, data_test = data
    config = configs[str(exp)]
    cfg.model.alpha = config["alpha"]
    cfg.model.lmd = config["hyperparams"]["lmd"]
    cfg.train.lr = config["hyperparams"]["lr"]
    cfg.train.early_stopping_rounds = config["hyperparams"]["early_stopping_rounds"]

    model = CAE(cfg.model)
    trainer = Trainer(cfg.train)
    trainer.fit(model, data_train, data_valid)

    X_test, y_test = data_test[:, :, :-1], data_test[:, :, -1].numpy()
    X_testp, outclass_testp, _ = model(X_test)
    X_testp = X_testp.detach().numpy()
    probs_testp = torch.nn.functional.softmax(outclass_testp, dim=1)
    y_testp = torch.argmax(probs_testp, dim=1).detach().numpy()

    cm = confusion_matrix(y_test, y_testp)
    acc = np.sum(np.diag(cm)) / np.sum(cm)
    np.seterr(all="ignore")  # Ignore warnings of divisions by 0
    cors = [
        distance_corr(X_testp[i, 0], X_test[i, 0].detach().numpy(), n_boot=None)
        for i in range(X_test.shape[0])
    ]
    cors = np.nan_to_num(cors)  # If division by 0 use cor = 0
    cor = np.mean(cors)
    print(f"END exp {exp} seed {seed}. acc={acc:.8f}, cor={cor:.8f} in {time.time()-tini:.1f}s")
    return acc, cor


def print_results(res, alphas, num_samples):
    print(res)
    num_alphas = len(alphas)
    accs = [
        list(x[0] for x in res[i*num_samples : (i+1)*num_samples])
        for i in range(num_alphas)
    ]
    cors = [
        list(x[1] for x in res[i*num_samples : (i+1)*num_samples])
        for i in range(num_alphas)
    ]
    print("accs:")
    print(accs)
    print("cors:")
    print(cors)

    cors_mean = np.array([np.mean(x) for x in cors])
    cors_std = np.array([np.std(x) for x in cors])
    accs_mean = np.array([np.mean(x) for x in accs])
    accs_std = np.array([np.std(x) for x in accs])

    plt.plot(alphas, cors_mean, "o-", label="Correlation")
    plt.fill_between(
        alphas, cors_mean - 2*cors_std, cors_mean + 2*cors_std, alpha=0.1
    )
    plt.plot(alphas, accs_mean, "o-", label="Accuracy")
    plt.fill_between(
        alphas, accs_mean - 2*accs_std, accs_mean + 2*accs_std, alpha=0.1
    )

    plt.legend()
    plt.xlabel("alpha")
    plt.savefig("alpha-cor_acc.png", dpi=100)


def main(
    dl=ARMA(5),
    alphas=[float(f) for f in np.linspace(0, 1, 21)],
    num_samples=8
):
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_cpus", type=int)
    parser.add_argument("--json", default="tuning.json", help="json with stored results.")
    parser.add_argument("--config_name", default="arma5", help="Config file.")
    args = parser.parse_args()

    ray.init(include_dashboard=False, num_cpus=args.num_cpus)

    vals = list(product(range(len(alphas)), range(num_samples)))

    data_train, data_valid, data_test = dl()

    with open(args.json) as f:
        configs = json.load(f)

    with initialize(config_path="configs"):
        cfg = compose(config_name=args.config_name)

    # Serialize data
    data_id = ray.put((data_train, data_valid, data_test))
    cfg_id, configs_id = ray.put(cfg), ray.put(configs)

    res = ray.get([acc_cor.remote(x, data_id, cfg_id, configs_id) for x in vals])
    print_results(res, alphas, num_samples)


if __name__ == "__main__":
    main()
