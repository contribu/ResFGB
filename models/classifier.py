# coding : utf-8

from __future__ import print_function, absolute_import, division, unicode_literals
import logging
import time
from utils import minibatches
from models.model import Model
import numpy as np

class Classifier(Model):
    def __init__( self, eta, scale, minibatch_size, seed ):
        """
        eta            : float.
        scale          : float
        minibatch_size : integer.
                         Minibatch size to calcurate stochastic gradient.
        seed           : integer.
                         Seed for random module.
        """
        super( Classifier, self ).__init__( seed )

        self.__eta          = eta
        self.__scale        = scale
        self.minibatch_size = minibatch_size

    def evaluate( self, Z, Y ):
        n, nc, loss = 0, 0, 0.
        minibatch_size = np.min( (10000, Z.shape[0]) )
        for (Zb,Yb) in minibatches( minibatch_size, Z, Y, shuffle=False ):
            (loss_,n_,nc_) = self.__calc_accuracy( Zb, Yb )
            loss = (n/(n+n_))*loss + (n_/(n+n_))*loss_
            n   += n_
            nc  += nc_
        acc = nc/n

        return loss, acc

    def __calc_accuracy( self, Z, Y):
        n = float( len(Y) )
        loss = self.loss_func(Z,Y)
        reg = self.reg_func()
        pred = self.predict(Z) 
        n_correct = np.sum( [ int(py==y) for (py,y) in zip(pred,Y) ] )
        return (loss + reg, n, n_correct )

    def evaluate_eta( self, X, Y, eta, eval_iters ):
        self.save_params()
        self.optimizer.set_eta(eta)

        n_iters = 0
        eval_f = True
        while eval_f:
            for (Xb,Yb) in minibatches( self.minibatch_size, X, Y, shuffle=True ):
                if n_iters >= eval_iters:
                    eval_f = False
                    break
                self.optimizer.update_func(Xb,Yb)
                n_iters += 1

        val = self.evaluate(X,Y)[0]
        self.load_params()
        self.optimizer.reset_func()

        return val

    def determine_eta( self, X, Y, eval_iters=10000, factor=2.,
                       level=logging.INFO ):
        val0     = self.evaluate( X, Y )[0]

        low_eta  = self.__eta
        low_val  = self.evaluate_eta( X, Y, low_eta,  eval_iters )
        low_val = np.inf if np.isnan( low_val ) else low_val

        high_eta = factor * low_eta
        high_val = self.evaluate_eta( X, Y, high_eta, eval_iters )
        high_val = np.inf if np.isnan( high_val ) else high_val

        decrease_f = True if ( np.isinf(low_val) 
                               or low_val < high_val 
                               or val0 < low_val 
                               or val0 < high_val ) else False

        if decrease_f:
            while low_val < high_val or np.isinf(low_val) or val0 < low_val:
                high_eta = low_eta
                high_val = low_val
                low_eta  = high_eta / factor
                low_val  = self.evaluate_eta( X, Y, low_eta, eval_iters )
                low_val  = np.inf if np.isnan( low_val ) else low_val
                self.__eta = high_eta 
        else:
            while low_val > high_val:
                low_eta  = high_eta
                low_val  = high_val
                high_eta = low_eta * factor
                high_val = self.evaluate_eta( X, Y, high_eta, eval_iters )
                high_val = np.inf if np.isnan( high_val ) else high_val
                self.__eta = low_eta 

        self.__eta *= self.__scale
        self.optimizer.set_eta( self.__eta )

        logging.log( level, 'determined_eta: {0}'.format( self.__eta ) )

    def fit( self, X, Y, max_epoch, Xv=None, Yv=None, early_stop=-1,
             set_best_param=False, level=logging.INFO ):
        """
        Run algorigthm for up to (max_eopch) epochs on training data X.
        
        Arguments
        ---------
        X          : Numpy array. 
                     Training data.
        Y          : numpy array.
                     Training label.
        max_epoch  : Integer.
        Xv         : Numpy array.
                     Validation data.
        Yv         : Numpy array.
                     Validation label.
        early_stop : Integer.
        """

        logging.log( level, '- Training -' )

        best_val_loss = 1e+10
        best_val_acc  = 0.
        best_param    = None
        best_epoch    = None
        val_results   = []
        total_time = 0.
        best_loss = 1e+10

        monitor = True if Xv is not None else False

        self.save_params()
        success = False

        init_train_loss, init_train_acc = self.evaluate( X, Y )

        while success is False:
            success = True

            for e in range(max_epoch):
                stime = time.time()
                for (Xb,Yb)  in minibatches( self.minibatch_size,
                                             X, Y, shuffle=True ):
                    self.optimizer.update_func(Xb,Yb)
                etime = time.time()
                total_time += etime-stime

                train_loss, train_acc = self.evaluate( X, Y )
                if np.isnan(train_loss) or np.isinf(train_loss) \
                   or (2*init_train_loss + 1) <= train_loss:
                    eta = self.optimizer.get_eta() / 2.
                    self.optimizer.set_eta( eta )
                    success = False
                    self.__load_param()
                    self.optimizer.reset_func()
                    logging.log( level,  'the learning process diverged' )
                    logging.log( level,  'retrain a model with a smaller learning rate: {0}'\
                                 .format( eta ) )
                    break

                logging.log( level,  'epoch: {0:4}, time: {1:>13.1f} sec'\
                             .format( e, total_time ) )
                logging.log( level,  'train_loss: {0:5.4f}, train_acc: {1:4.3f}'\
                             .format( train_loss, train_acc ) )

                if monitor:
                    val_loss, val_acc = self.evaluate( Xv, Yv )
                    logging.log( level,  'val_loss  : {0:5.4f}, val_acc  : {1:4.3f}'\
                                 .format( val_loss, val_acc ) )

                    val_results.append( ( {'epoch' : e+1},
                                          val_loss, val_acc) )
                
                    if val_loss < best_val_loss:
                        best_epoch    = e+1
                        best_val_loss = val_loss
                        best_val_acc  = val_acc
                        best_param    = self.get_params( real_f=True )
                
                # early_stopping
                if train_loss < 0.999*best_loss:
                    best_loss = train_loss
                    best_epoch = e

                if early_stop > 0 and e - best_epoch >= early_stop:
                    success = True
                    break

        if monitor and set_best_param:
            if best_epoch < self.epoch:
                self.set_param( best_param )

        return val_results