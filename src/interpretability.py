import torch
import numpy as np
from torch import optim

def shapley_sampling(x, model, feature, n_batches=1, batch_size=64):
    length = x.shape[-1]
    sv = torch.zeros(length)

    x = x.reshape(1, length).repeat(batch_size, 1)
    for _ in range(n_batches):
        y = torch.rand((batch_size, length))
        O = np.array([np.random.permutation(length) for _ in range(batch_size)])
        idx = np.where(O == feature)
        Os = [O[i,:j] for i, j in zip(idx[0], idx[1])]

        sel = torch.zeros((batch_size,length), dtype=torch.bool)
        sel[np.concatenate([np.repeat(i,len(Os[i])) for i in range(batch_size)]), np.concatenate(Os)] = True

        x2 = torch.where(sel, x, y)
        x1 = x2.clone()
        x1[:,feature] = x[:,feature]

        x1 = x1.reshape(-1,1,length)
        x2 = x2.reshape(-1,1,length)
        with torch.no_grad():
            v1 = model(x1, False)[0][:,0]
            v2 = model(x2, False)[0][:,0]
        sv += torch.sum(v1 - v2, axis=0)

    sv /= n_batches*batch_size
    return sv.numpy()

def shapley_sampling_bottleneck(x, model, feature, baselines=None, n_batches=1, batch_size=64):
    sv = torch.zeros(x.shape[-1])
    x = model.encoder(x.reshape(1,1,96), False) # bottleneck
    length = x.shape[-1]
    for _ in range(n_batches):
        if baselines is None:
            y = torch.zeros((batch_size, length)) # changed
        else:
            y = torch.tensor(baselines).reshape(1,24).repeat((batch_size,1))
        O = np.array([np.random.permutation(length) for _ in range(batch_size)])
        idx = np.where(O == feature)
        Os = [O[i,:j] for i, j in zip(idx[0], idx[1])]

        sel = torch.zeros((batch_size,length), dtype=torch.bool)
        sel[np.concatenate([np.repeat(i,len(Os[i])) for i in range(batch_size)]), np.concatenate(Os)] = True

        x2 = torch.where(sel, x, y)
        x1 = x2.clone()
        x1[:,feature] = x[:,feature]

        x1 = x1.reshape(-1,1,length)
        x2 = x2.reshape(-1,1,length)
        with torch.no_grad():
            v1 = model.decoder(x1)[:,0]
            v2 = model.decoder(x2)[:,0]
        sv += torch.sum(v1 - v2, axis=0)

    sv /= n_batches*batch_size
    return sv.numpy()

def feature_visualization(model, neuron):
    """
    https://pytorch.org/tutorials/advanced/neural_style_tutorial.html
    """
    X = torch.rand((1,1,96), requires_grad=True)
    optimizer = optim.LBFGS([X])

    def closure():
        optimizer.zero_grad()
        model.zero_grad()
        _, _, bn = model(torch.sigmoid(X), apply_noise=False)
        y = -bn[0,neuron]
        y.backward()
        return y

    for i in range(100):
        optimizer.step(closure)
    return torch.sigmoid(X).detach().numpy().flatten()

def feature_visualization_class(model, clss):
    """"
    https://pytorch.org/tutorials/advanced/neural_style_tutorial.html
    """
    X = torch.rand((1,1,96), requires_grad=True)
    optimizer = optim.LBFGS([X])

    def closure():
        optimizer.zero_grad()
        model.zero_grad()
        _, pred_class, _ = model(torch.sigmoid(X), apply_noise=False)
        y = -pred_class[0,clss]
        y.backward()
        return y

    for i in range(100):
        optimizer.step(closure)
    return torch.sigmoid(X).detach().numpy().flatten()