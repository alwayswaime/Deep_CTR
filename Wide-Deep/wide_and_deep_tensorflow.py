import pandas as pd
import numpy as np
import tensorflow as tf
from sklearn.preprocessing import LabelEncoder, MinMaxScaler
from sklearn.metrics import roc_auc_score, accuracy_score, log_loss, mean_squared_error
import time
from tensorflow.contrib.layers.python.layers import batch_norm

'''
wide part: auc = 0.75459
deep part: auc = 0.885174
wide&deep: auc = 0.88815
'''

class Wide_Deep:
    '''
    
    optimizer_type: adam, adagrad, gd, momentum, rmsprop
    loss_type: logloss, mse
    metric_type: auc, accuracy, logloss, rmse
    '''
    def __init__(self, continuous_feature, category_feature, cross_feature=[], embedding_size=8, deep_layers=[32, 32],
                 dropout_deep=[0.5, 0.5, 0.5], deep_layers_activation=tf.nn.relu, epochs=10, batch_size=128, learning_rate=0.001, optimizer_type='adam',
                 random_seed=2018, loss_type='logloss', metric_type='auc', l2_reg=0.0):
        self.continuous_feature = continuous_feature
        self.category_feature = category_feature
        self.cross_feature = cross_feature
        self.embedding_size = embedding_size
        self.deep_layers = deep_layers
        self.dropout_deep = dropout_deep
        self.deep_layers_activation = deep_layers_activation
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.optimizer_type = optimizer_type
        self.random_seed = random_seed
        self.loss_type = loss_type
        self.metric_type = metric_type
        self.l2_reg = l2_reg

    def preprocessing(self, train, test):
        train['income_label'] = train['income_label'].apply(lambda x: '>50K' in x).astype(int)
        test['income_label'] = test['income_label'].apply(lambda x: '>50K' in x).astype(int)
        train['is_train'] = 1
        test['is_train'] = 0
        data = pd.concat([train, test], axis=0)

        # labelencoder
        lbc = LabelEncoder()
        print('label encoder start...')
        for feature in self.category_feature:
            print("this is feature:", feature)
            try:
                data[feature] = lbc.fit_transform(data[feature].apply(int))
            except:
                data[feature] = lbc.fit_transform(data[feature].astype(str))

        scaler = MinMaxScaler()
        for feature in continuous_feature:
            data[feature] = scaler.fit_transform(data[feature].values.reshape(-1, 1))

        train = data[data['is_train'] == 1].drop('is_train', axis=1)
        test = data[data['is_train'] == 0].drop('is_train', axis=1)

        self.y_train = train['income_label'].values.reshape(-1, 1)
        self.train = train.drop('income_label', axis=1)
        self.y_val = test['income_label'].values.reshape(-1, 1)
        self.test = test.drop('income_label', axis=1)

    def fit(self, train, test):
        self.preprocessing(train, test)
        self.graph = tf.Graph()
        with self.graph.as_default():
            tf.set_random_seed(self.random_seed)
            self.feature_size = len(self.continuous_feature) + len(self.category_feature) + len(self.cross_feature)
            self.cont_feats = tf.placeholder(tf.float32, shape=[None, None], name='continuous_feature')
            self.cate_feats = tf.placeholder(tf.int32, shape=[None, None], name='category_feature')
            self.cross_feats = tf.placeholder(tf.int32, shape=[None, None], name='cross_feature')
            self.input = tf.placeholder(tf.float32, shape=[None,  self.feature_size], name='input')
            self.label = tf.placeholder(tf.float32, shape=[None, 1], name='label')

            weights = {}
            biases = {}


            with tf.name_scope('wide_part'):
                weights['wide_w'] = tf.Variable(tf.random_normal([self.feature_size, 1]))
                biases['wide_b'] = tf.Variable(tf.random_normal([1]))

                # self.wide_out = tf.add(tf.matmul(self.input, weights['wide_w']), biases['wide_b'])
                self.wide_out = self.input

            with tf.name_scope('deep_part'):
                num_layer = len(self.deep_layers)
                # weights['deep_layer_0'] = tf.Variable(tf.random_normal([self.feature_size, self.deep_layers[0]]))
                # biases['deep_layer_bias_0'] = tf.Variable(tf.random_normal([self.deep_layers[0]]))
                # for i in range(1, num_layer):
                #     weights['deep_layer_%s' % i] = tf.Variable(tf.random_normal([self.deep_layers[i - 1], self.deep_layers[i]]))
                #     biases['deep_layer_bias_%s' % i] = tf.Variable(tf.random_normal([self.deep_layers[i]]))
                #
                # self.deep_out = tf.reshape(self.input, shape=[-1, self.feature_size])
                # for i in range(len(self.deep_layers)):
                #     self.deep_out = tf.add(tf.matmul(self.deep_out, weights['deep_layer_%s' % i]), biases['deep_layer_bias_%s' % i])
                #     self.deep_out = self.deep_layers_activation(self.deep_out)

                self.deep_out = tf.keras.layers.Dense(self.deep_layers[0], activation=self.deep_layers_activation)(self.input)
                for i in range(1, num_layer):
                    self.deep_out = tf.keras.layers.Dense(self.deep_layers[i], activation=self.deep_layers_activation)(self.deep_out)


            with tf.name_scope('concat_wide_deep'):
                # input_size = 1 + self.deep_layers[-1]
                input_size = self.feature_size + self.deep_layers[-1]
                weights['concat_projection'] = tf.Variable(tf.random_normal([input_size, 1]), dtype=np.float32)
                biases['concat_bias'] = tf.Variable(tf.constant(0.01), dtype=np.float32)
                concat_input = tf.concat([self.wide_out, self.deep_out], axis=1)

                self.out = tf.add(tf.matmul(concat_input, weights['concat_projection']), biases['concat_bias'])

            # loss
            if self.loss_type == 'logloss':
                self.out = tf.nn.sigmoid(self.out)
                self.loss = tf.losses.log_loss(self.label, self.out)

            elif self.loss_type == 'mse':
                self.loss = tf.nn.l2_loss(tf.subtract(self.label, self.out))

            # l2 regularization on weights
            if self.l2_reg > 0:
                for i in range(len(self.deep_layers)):
                    self.loss = self.loss + self.l2_reg * (tf.nn.l2_loss(weights['deep_layer_%s' % i]) + tf.nn.l2_loss(weights['deep_layer_bias_%s' % i]))

            # optimizer
            if self.optimizer_type == 'adam':
                self.optimizer = tf.train.AdamOptimizer(learning_rate=self.learning_rate).minimize(self.loss)

            elif self.optimizer_type == 'adagrad':
                self.optimizer = tf.train.AdagradOptimizer(learning_rate=self.learning_rate, initial_accumulator_value=1e-8).minimize(self.loss)

            elif self.optimizer_type == 'gd':
                self.optimizer = tf.train.GradientDescentOptimizer(learning_rate=self.learning_rate).minimize(self.loss)

            elif self.optimizer_type == 'momentum':
                self.optimizer = tf.train.MomentumOptimizer(learning_rate=self.learning_rate, momentum=0.95).minimize(self.loss)

            elif self.optimizer_type == 'rmsprop':
                self.optimizer = tf.train.RMSPropOptimizer(learning_rate=self.learning_rate).minimize(self.loss)

            init = tf.global_variables_initializer()
            self.sess = tf.Session()
            self.sess.run(init)

            total_time = 0

            # train
            for epoch in range(self.epochs):
                start_time = time.time()
                for i in range(0, len(self.train), self.batch_size):
                    batch_x, batch_y = self.train[i: i + self.batch_size], self.y_train[i: i + self.batch_size]
                    feed_dict = {
                        self.input: batch_x,
                        self.label: batch_y
                    }
                    cost, opt = self.sess.run([self.loss, self.optimizer], feed_dict=feed_dict)
                pred = self.predict(batch_x)
                auc = self.evaluate(batch_x, batch_y)
                end_time = time.time()
                total_time = total_time + end_time - start_time
                print('Epoch=%s, cost=%s, auc=%s, time=%s s' % (epoch + 1, cost, auc, total_time))
    
    def predict(self, train):
        feed_dict = {
            self.input: train
        }
        y_pred = self.sess.run(self.out, feed_dict=feed_dict)
        return y_pred

    def evaluate(self, train, label):
        y_pred = self.predict(train)
        if self.metric_type == 'auc':
            metric = roc_auc_score(label, y_pred)
        elif self.metric_type == 'accuracy':
            metric = accuracy_score(label, y_pred)
        elif self.metric_type == 'logloss':
            metric = log_loss(label, y_pred)
        elif self.metric_type == 'rmse':
            metric = mean_squared_error(label, y_pred)
        return metric

if __name__ == '__main__':
    print('读取数据...')
    columns = ['age', 'workclass', 'fnlwgt', 'education', 'education_num', 'marital_status', 'occupation',
               'relationship', 'race', 'sex',
               'capital_gain', 'capital_loss', 'hours_per_week', 'native_country', 'income_label']
    train = pd.read_csv('data/adult.data', names=columns, skipinitialspace=True)
    test = pd.read_csv('data/adult.test', names=columns, skipinitialspace=True)

    continuous_feature = ['age', 'fnlwgt', 'education_num', 'capital_gain', 'capital_loss', 'hours_per_week']
    category_feature = ['workclass', 'education', 'marital_status', 'occupation', 'relationship', 'race', 'sex',
                        'native_country']

    wide_deep = Wide_Deep(continuous_feature, category_feature)
    wide_deep.fit(train, test)
