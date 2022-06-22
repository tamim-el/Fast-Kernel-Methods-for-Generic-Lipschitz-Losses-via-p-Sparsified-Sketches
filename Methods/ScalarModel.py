import numpy as np
from scipy import linalg
from sklearn.metrics import mean_absolute_error
from sklearn.metrics import mean_squared_error

class ScalarModel:

    def __init__(self, kernel, Sketch=None, L=1., algo='krr',
                 alg_param=0.5, optim='adam', max_iter=1000,
                 lr=1e-3, tol=1e-3, monitoring_step=1,
                 early_stopping=False, n_iter_no_change=5,
                 score=mean_squared_error, verbose=False):
        # Saving parameters
        self.kernel = kernel
        self.Sketch = Sketch
        self.L = L
        self.algo = algo
        self.alg_param = alg_param
        self.loss = choice_loss(algo=self.algo, param=self.alg_param)
        self.loss_vect = choice_loss_vect(algo=self.algo, param=self.alg_param)
        self.grad = choice_grad(algo=self.algo, param=self.alg_param)
        self.optim = optim
        self.max_iter = max_iter
        self.lr = lr
        self.tol = tol
        self.monitoring_step = monitoring_step
        self.early_stopping =early_stopping
        self.n_iter_no_change = n_iter_no_change
        self.score = score
        self.verbose = verbose

    def fit(self, X_tr, Y_tr, X_val=None, Y_val=None):
        # Training
        self.X_tr = X_tr.copy()
        self.Y_tr = Y_tr.copy()
        self.n_tr = self.X_tr.shape[0]

        if self.algo == 'krr':
            # Without sketching
            if self.Sketch is None:
                K_x = self.kernel(self.X_tr, Y=self.X_tr)
                M = K_x + self.n_tr * self.L * np.eye(self.n_tr)
                self.w = np.linalg.inv(M).dot(self.Y_tr)
            # With sketching
            else:
                S = self.Sketch
                K_x = S.multiply_Gram_both_sides(self.X_tr, self.kernel)
                K_x_S = S.multiply_Gram_one_side(self.X_tr, self.kernel, self.X_tr)
                M = K_x_S.T.dot(K_x_S) + self.n_tr * self.L * K_x
                M_inv = np.linalg.pinv(M)
                Y_s = K_x_S.T.dot(self.Y_tr)
                self.w = M_inv.dot(Y_s)

        elif self.algo in ['e_krr', 'e_svr', 'k_huber', 'svm']:

            # Without sketching
            if self.Sketch is None:

                self.w, self.objectives, self.train_loss, self.val_loss, self.train_score, self.val_score = sgd(X_tr, Y_tr, X_val, Y_val,
                                                                                                                self.kernel, self.L, self.algo,
                                                                                                                self.loss_vect, self.grad,
                                                                                                                self.optim, self.lr,
                                                                                                                self.max_iter, self.tol,
                                                                                                                self.monitoring_step,
                                                                                                                self.early_stopping,
                                                                                                                self.n_iter_no_change,
                                                                                                                self.score, self.verbose)

            # With sketching
            else:

                S = self.Sketch
                SKST = S.multiply_Gram_both_sides(self.X_tr, self.kernel)
                V, D, _ = np.linalg.svd(SKST)
                nnz_D = np.logical_not(np.isclose(D, np.zeros(D.shape), rtol=1e-12,))
                D_r, V_r = D[nnz_D], V[:, nnz_D]
                self.A = (D_r ** (-1/2)) * V_r
                self.w, self.objectives, self.train_loss, self.val_loss, self.train_score, self.val_score = sgd_sketch(X_tr, Y_tr, X_val, Y_val,
                                                                                                                        self.A, self.kernel, S,
                                                                                                                        self.L, self.algo,
                                                                                                                        self.loss_vect, self.grad,
                                                                                                                        self.optim, self.lr,
                                                                                                                        self.max_iter, self.tol,
                                                                                                                        self.monitoring_step,
                                                                                                                        self.early_stopping,
                                                                                                                        self.n_iter_no_change,
                                                                                                                        self.score, self.verbose)

    def predict(self, X_te):
        # Without sketching
        if self.Sketch is None:
            K_x_te_tr = self.kernel(X_te, self.X_tr)
            Y_pred = K_x_te_tr.dot(self.w)
        # With sketching
        else:
            S = self.Sketch
            KS = S.multiply_Gram_one_side(X_te, self.kernel, Y=self.X_tr)
            if self.algo == 'krr':
                Y_pred = KS.dot(self.w)
            else:
                Z_te = (KS).dot(self.A)
                Y_pred = Z_te.dot(self.w)
        return Y_pred


def Huber(x, kappa):
    if x >= kappa:
        return kappa * (x - kappa / 2)
    elif x < -kappa:
        return -kappa * (x + kappa / 2)
    else:
        return (x ** 2) / 2

def Huber_vect(x, kappa):
    res = (x ** 2) / 2
    res[np.where(x >= kappa)] = kappa * (x[np.where(x >= kappa)] - kappa / 2)
    res[np.where(x < -kappa)] = -kappa * (x[np.where(x < -kappa)] + kappa / 2)
    return res

def grad_Huber(x, kappa):
    if x >= kappa:
        return kappa
    elif x < -kappa:
        return -kappa
    else:
        return x


def eL2(x, eps):
    if x >= eps:
        return (x - eps) ** 2
    elif x < -eps:
        return (x + eps) ** 2
    else:
        return 0

def eL2_vect(x, eps):
    res = np.zeros_like(x)
    res[np.where(x >= eps)] = (x[np.where(x >= eps)] - eps) ** 2
    res[np.where(x < -eps)] = (x[np.where(x < -eps)] + eps) ** 2
    return res

def grad_eL2(x, eps):
    if x >= eps:
        return 2 * (x - eps)
    elif x < -eps:
        return 2 * (x + eps)
    else:
        return 0


def eL1(x, eps):
    if x >= eps:
        return x - eps
    elif x < -eps:
        return -(x + eps)
    else:
        return 0

def eL1_vect(x, eps):
    res = np.zeros_like(x)
    res[np.where(x >= eps)] = (x[np.where(x >= eps)] - eps)
    res[np.where(x < -eps)] = -(x[np.where(x < -eps)] + eps)
    return res

def grad_eL1(x, eps):
    if x >= eps:
        return 1
    elif x <= -eps:
        return -1
    else:
        return 0


def Hinge(x):
    if x <= 1:
        return 1 - x
    else:
        return 0

def Hinge_vect(x, eps):
    res = 1 - x
    res[np.where(x > 1)] = 0
    return res

def grad_Hinge(x):
    if x <= 1:
        return -1
    else:
        return 0


def choice_loss(algo='svm', param=None):
    if algo == 'svm':
        def loss(x):
            return Hinge(x)
    elif algo == 'e_krr':
        def loss(x):
            return eL2(x, param)
    elif algo == 'e_svr':
        def loss(x):
            return eL1(x, param)
    else:
        def loss(x):
            return Huber(x, param)
    return loss


def choice_loss_vect(algo='svm', param=None):
    if algo == 'svm':
        def loss_vect(x):
            return Hinge_vect(x)
    elif algo == 'e_krr':
        def loss_vect(x):
            return eL2_vect(x, param)
    elif algo == 'e_svr':
        def loss_vect(x):
            return eL1_vect(x, param)
    else:
        def loss_vect(x):
            return Huber_vect(x, param)
    return loss_vect


def choice_grad(algo='svm', param=None):
    if algo == 'svm':
        def grad(x):
            return grad_Hinge(x)
    elif algo == 'e_krr':
        def grad(x):
            return grad_eL2(x, param)
    elif algo == 'e_svr':
        def grad(x):
            return grad_eL1(x, param)
    else:
        def grad(x):
            return grad_Huber(x, param)
    return grad


def sgd_sketch(X_tr, Y_tr, X_val, Y_val, A, kernel, S,
               L, algo, loss_vect, grad, optim, lr, max_iter,
               tol=1e-3, monitoring_step=100, early_stopping=False,
               n_iter_no_change=5, score=mean_squared_error,
               verbose=False):
    """
        Stochastic Gradient Descent for linear primal pb with sketched feature maps
    """
    # Computation of sketched feature maps
    KS = S.multiply_Gram_one_side(X_tr, kernel)
    Z_tr = KS.dot(A)
    # For validation set if early_stopping
    if early_stopping:
        KvalS = S.multiply_Gram_one_side(X_val, kernel, Y=X_tr)
        Z_val = (KvalS).dot(A)

    # Init weights
    r = A.shape[1]
    w = np.zeros(r)
    n_tr = X_tr.shape[0]

    # Init moments and exp decays if adam used
    if optim == 'adam':
        beta1, beta2 = 0.9, 0.999
        m, v = 0, 0
        eps = 1e-8

    # Init monitoring
    objectives = []
    train_loss = []
    val_loss = []
    train_score = []
    val_score = []

    count_monitoring = 0
    stop = False

    # Iterations over epochs
    for iter in range(max_iter):
        
        # Iterations over training set
        for i in range(n_tr):
            t = n_tr * iter + i + 1
            # Computation of gradient
            yi = Y_tr[i]
            feature = Z_tr[i, :]
            if algo == 'svm':
                grad_l = grad(yi * w.dot(feature))
                gradient = L * w + grad_l * yi * feature
            else:
                grad_l = grad(w.dot(feature) - yi)
                gradient = L * w + grad_l * feature
            # Update
            if optim == 'sgd':
                w = w - lr * gradient
            else:
                m = beta1 * m + (1 - beta1) * gradient
                v = beta2 * v + (1 - beta2) * (gradient ** 2)
                mhat = m / (1 - (beta1 ** t))
                vhat = v / (1 - (beta2 ** t))
                w = w - lr * mhat / ((vhat ** (1/2)) + eps)

            # Monitoring
            if (i + 1) % monitoring_step == 0:
                count_monitoring += 1
                # Computation of train loss and objective function
                pred_tr = Z_tr.dot(w)
                if algo == 'svm':
                    predy_tr = pred_tr * Y_tr
                else:
                    predy_tr = pred_tr - Y_tr
                losses = loss_vect(predy_tr)
                train_loss.append(np.mean(losses))
                objectives.append(train_loss[-1] + (L / 2) * np.linalg.norm(w))

                # Computation of validation loss
                if early_stopping:
                    pred_val = Z_val.dot(w)
                    if algo == 'svm':
                        predy_val = pred_val * Y_val
                    else:
                        predy_val = pred_val - Y_val
                    losses = loss_vect(predy_val)
                    val_loss.append(np.mean(losses))

                # Computation of train and validation score
                train_score.append(score(pred_tr, Y_tr))
                if early_stopping:
                    val_score.append(score(pred_val, Y_val))

                # Stopping criterion and early stopping
                if tol is not None:

                    if count_monitoring > n_iter_no_change:

                        if np.abs(objectives[1] - objectives[0]) == 0:
                            norm_crit = 1
                        else:
                            norm_crit = np.abs(objectives[1] - objectives[0])

                        # Stopping criterion for objective
                        if False not in (np.asarray(objectives[-n_iter_no_change - 1 : -1]) - np.asarray(objectives[-n_iter_no_change:]) < tol * norm_crit):
                            if verbose:
                                print("Stopping criterion attained at epoch: " + str(iter))
                            stop = True
                            break

                        # Early stopping for validation score
                        if early_stopping:

                            if np.abs(val_score[1] - val_score[0]) == 0:
                                norm_es = 1
                            else:
                                norm_es = np.abs(val_score[1] - val_score[0])

                            if False not in (np.asarray(val_score[-n_iter_no_change - 1 : -1]) - np.asarray(val_score[-n_iter_no_change:]) < tol * norm_es):
                                if verbose:
                                    print("Early stopping attained at epoch: " + str(iter))
                                stop = True
                                break

        if stop:
            break

    return w, objectives, train_loss, val_loss, train_score, val_score


def sgd(X_tr, Y_tr, X_val, Y_val, kernel, L,
        algo, loss_vect, grad, optim, lr, max_iter,
        tol=1e-3, monitoring_step=100, early_stopping=False,
        n_iter_no_change=5, score=mean_squared_error,
        verbose=False):
    """
        Stochastic Gradient Descent for primal pb without sketching
    """
    # Computation of K
    K = kernel(X_tr, X_tr)
    # For validation set if early_stopping
    if early_stopping:
        K_valtr = kernel(X_val, X_tr)

    # Init weights
    n_tr = X_tr.shape[0]
    w = np.zeros(n_tr)

    # Init moments and exp decays if adam used
    if optim == 'adam':
        beta1, beta2 = 0.9, 0.999
        m, v = 0, 0
        eps = 1e-8

    # Init monitoring
    objectives = []
    train_loss = []
    val_loss = []
    train_score = []
    val_score = []

    count_monitoring = 0
    stop = False

    # Iterations over epochs
    for iter in range(max_iter):
        
        # Iterations over training set
        for i in range(n_tr):
            t = n_tr * iter + i + 1
            # Computation of gradient
            yi = Y_tr[i]
            k = K[i, :]
            if algo == 'svm':
                grad_l = grad(yi * w.dot(k))
                gradient = L * K.dot(w) + grad_l * yi * k
            else:
                grad_l = grad(w.dot(k) - yi)
                gradient = L * K.dot(w) + grad_l * k
            # Update
            if optim == 'sgd':
                w = w - lr * gradient
            else:
                m = beta1 * m + (1 - beta1) * gradient
                v = beta2 * v + (1 - beta2) * (gradient ** 2)
                mhat = m / (1 - (beta1 ** t))
                vhat = v / (1 - (beta2 ** t))
                w = w - lr * mhat / ((vhat ** (1/2)) + eps)

            # Monitoring
            if (i + 1) % monitoring_step == 0:
                count_monitoring += 1
                # Computation of train loss and objective function
                pred_tr = K.dot(w)
                if algo == 'svm':
                    predy_tr = pred_tr * Y_tr
                else:
                    predy_tr = pred_tr - Y_tr
                losses = loss_vect(predy_tr)
                train_loss.append(np.mean(losses))
                objectives.append(train_loss[-1] + (L / 2) * w.dot(K).dot(w))

                # Computation of validation loss
                if early_stopping:
                    pred_val = K_valtr.dot(w)
                    if algo == 'svm':
                        predy_val = pred_val * Y_val
                    else:
                        predy_val = pred_val - Y_val
                    losses = loss_vect(predy_val)
                    val_loss.append(np.mean(losses))

                # Computation of train and validation score
                train_score.append(score(pred_tr, Y_tr))
                if early_stopping:
                    val_score.append(score(pred_val, Y_val))

                # Stopping criterion and early stopping
                if tol is not None:

                    if count_monitoring > n_iter_no_change:

                        #best_objective = np.min(objectives)

                        if np.abs(objectives[1] - objectives[0]) == 0:
                            norm_crit = 1
                        else:
                            norm_crit = np.abs(objectives[1] - objectives[0])

                        # Stopping criterion for objective
                        if False not in (np.asarray(objectives[-n_iter_no_change - 1 : -1]) - np.asarray(objectives[-n_iter_no_change:]) < tol * norm_crit):
                        #if False not in (np.asarray(objectives[-n_iter_no_change:]) - best_objective < tol * norm_crit):
                            if verbose:
                                print("Stopping criterion attained at epoch: " + str(iter))
                            stop = True
                            break

                        # Early stopping for validation score
                        if early_stopping:

                            #best_val_score = np.min(val_score)

                            if np.abs(val_score[1] - val_score[0]) == 0:
                                norm_es = 1
                            else:
                                norm_es = np.abs(val_score[1] - val_score[0])

                            if False not in (np.asarray(val_score[-n_iter_no_change - 1 : -1]) - np.asarray(val_score[-n_iter_no_change:]) < tol * norm_es):
                            #if False not in (np.asarray(val_score[-n_iter_no_change - 1 : -1]) - best_val_score < tol * norm_es):
                                if verbose:
                                    print("Early stopping attained at epoch: " + str(iter))
                                stop = True
                                break

        if stop:
            break

    return w, objectives, train_loss, val_loss, train_score, val_score