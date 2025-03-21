
from keras.src.callbacks import LearningRateScheduler, EarlyStopping
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.metrics import accuracy_score, f1_score
from xgboost import XGBClassifier
from sklearn.linear_model import LogisticRegression
from keras.src.models import Model
from keras.src.layers import Dense, Dropout, Input,  BatchNormalization, concatenate
from keras.src.metrics import F1Score
from keras.src import regularizers
import numpy as np


from src.utils.config import config
from src.utils.constansts import IIM_MODELS, EXPERIMENTS

models = {
    IIM_MODELS.XGBOOST.value: XGBClassifier,
}

class TabularInternalModel(BaseEstimator, ClassifierMixin):
    def __init__(self, **kwargs):
        self.model = kwargs.get('model')
        self.name = "xgboost"

    def fit(self, X, y):
        self.model.fit(X, y)
        return self

    def predict(self, X):
        return self.model.predict(X)

    def predict_proba(self, X):
        return self.model.predict_proba(X)

    def evaluate(self, X, y):
        pred = self.predict(X)
        return accuracy_score(y, pred), f1_score(y, pred, average='weighted')



class NeuralNetworkInternalModel(BaseEstimator, ClassifierMixin):

    def __init__(self, **kwargs):
        self.batch_size = config.neural_net_config.batch_size
        self.dropout_rate = config.neural_net_config.dropout
        self.epochs = config.neural_net_config.epochs
        self.model: Model = None

    def fit(self, X, y):
        lr_scheduler = LearningRateScheduler(lambda epoch: 0.0001 * (0.9 ** epoch))
        early_stopping = EarlyStopping(patience=2, monitor='loss')
        self.model.fit(X, y, epochs=self.epochs, batch_size=self.batch_size, callbacks=[lr_scheduler, early_stopping])

    def predict(self, X):
        prediction = self.model.predict(X)
        return np.argmax(prediction, axis=1)

    def predict_proba(self, X):
        return self.model.predict(X)

    def evaluate(self, X, y):
        if len(y.shape) == 2:
            y = np.argmax(y, axis=1)

        pred = self.predict(X)
        return accuracy_score(y, pred), f1_score(y, pred, average='weighted')


class DenseInternalModel(NeuralNetworkInternalModel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "neural_network"
        num_classes = kwargs.get("num_classes")
        input_shape = kwargs.get("input_shape")
        self.model = self.get_model(num_classes=num_classes, input_shape=input_shape)

    def get_model(self, num_classes, input_shape):
        # Build the model
        inputs = Input(shape=(input_shape,))  # Dynamic input shape

        # Define the hidden layers
        x = BatchNormalization()(inputs)
        x = Dense(units=128, activation='leaky_relu')(x)
        x = Dropout(self.dropout_rate)(x)

        # Define the output layer
        outputs = Dense(units=num_classes, activation='softmax')(x)

        # Create the model
        model = Model(inputs=inputs, outputs=outputs)

        # Compile the model with F1 Score
        model.compile(optimizer='adam',
                      loss='categorical_crossentropy',
                      metrics=['accuracy', F1Score()]
                      )

        return model


class DoubleDenseInternalModel(NeuralNetworkInternalModel):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "neural_network"
        num_classes = kwargs.get("num_classes")
        input_shape = kwargs.get("input_shape")
        self.model = self.get_model(num_classes=num_classes, input_shape=input_shape)

    def get_model(self, num_classes, input_shape):
        inputs_sub_networks = []

        input_shape_a, input_shape_b = input_shape
        input_a = Input(shape=(input_shape_a,))

        x = Dense(input_shape_a // 2, activation="relu", kernel_regularizer=regularizers.L2(0.1), bias_regularizer=regularizers.L2(0.01))(
            input_a)
        x = BatchNormalization(momentum=0.7)(x)
        x = Dropout(0.3)(x)
        # x = Dense(input_shape_a / 2, activation="relu")(x)
        x = Model(inputs=input_a, outputs=x)

        inputs_sub_networks.append(x)

        input_b = Input(shape=(input_shape_b,))
        # the second branch operates on the second input
        y = Dense(input_shape_b // 4, activation="relu", kernel_regularizer=regularizers.L2(0.1),  bias_regularizer=regularizers.L2(0.01))(
            input_b)
        y = BatchNormalization(momentum=0.7)(y)
        y = Dropout(0.3)(y)
        y = Model(inputs=input_b, outputs=y)

        inputs_sub_networks.append(y)

        combined = concatenate([k.output for k in inputs_sub_networks])

        m = Dense(num_classes, activation="softmax", kernel_regularizer=regularizers.L2(0.1),
                  bias_regularizer=regularizers.L2(0.1))(combined)

        model = Model(inputs=[k.input for k in inputs_sub_networks], outputs=m)
        # Compile the model with F1 Score
        model.compile(optimizer='adam',
                      loss='categorical_crossentropy',
                      metrics=['accuracy', F1Score()]
                      )

        return model

class StackingInternalModel:

    name: str

    def __init__(self, **kwargs):
        self.models = None
        self.final_model = None


    def fit(self, X: list, y):
        assert len(X) == len(self.models), "Number of datasets, targets, and models must be the same"

        # Fit each model on its corresponding dataset
        for i, x in enumerate(X):
            self.models[i].fit(x, y)

        # Collect predictions from each model
        meta_features = []
        for i, x in enumerate(X):
            preds = self.models[i].predict_proba(x)
            meta_features.append(preds)

        # Stack predictions horizontally (axis=1) to form the meta-features
        meta_features = np.hstack(meta_features)

        # Fit the final model on the meta-features
        self.final_model.fit(meta_features, y)  # Assuming y is the target for the final model


    def predict(self, X):
        # Collect predictions from each model
        meta_features = []
        for i, x in enumerate(X):
            preds = self.models[i].predict_proba(x)
            meta_features.append(preds)

            # Stack predictions horizontally (axis=1) to form the meta-features
        meta_features = np.hstack(meta_features)

        # Predict using the final model
        return self.final_model.predict(meta_features)

    def evaluate(self, X, y):

        pred = self.predict(X)
        if len(y.shape) == 2 and len(pred.shape) == 1:
            y = y.argmax(axis=1)
        return accuracy_score(y, pred), f1_score(y, pred, average='weighted')



class StackingDenseInternalModel(StackingInternalModel):

    name = "neural_network_stacking_iim"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        num_models = len(config.cloud_config.names)
        self.models = [DenseInternalModel(**kwargs) for _ in range(num_models)]

        # For the final model, we need to init it according to the correct number of inputs. The final model will need a
        # different number of inputs which is num_classes * num_models
        input_size = num_models * kwargs.get("num_classes")
        kwargs['input_shape'] = input_size
        self.final_model = DenseInternalModel(**kwargs)


class StackingXGInternalModel(StackingInternalModel):

    name = "xg_stacking_iim"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        num_models = len(config.cloud_config.names)
        self.models = [XGBClassifier() for _ in range(num_models)]

        # For the final model, we need to init it according to the correct number of inputs. The final model will need a
        # different number of inputs which is num_classes * num_models
        input_size = num_models * kwargs.get("num_classes")
        kwargs['input_shape'] = input_size
        self.final_model = DenseInternalModel(**kwargs)


class StackingMixedInternalModel(StackingInternalModel):
    name = "logistic_xg_boost_stacking_iim"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        num_cloud_models = len(config.cloud_config.names)
        self.nn_models = [DenseInternalModel(**kwargs) for _ in range(num_cloud_models)]
        self.xg_models = [XGBClassifier() for _ in range(num_cloud_models)]
        self.ll_models = [LogisticRegression() for _ in range(num_cloud_models)]

        num_models = len(self.nn_models) + len(self.xg_models) + len(self.ll_models)
        # For the final model, we need to init it according to the correct number of inputs. The final model will need a
        # different number of inputs which is num_classes * num_models
        input_size = num_models * kwargs.get("num_classes")
        kwargs['input_shape'] = input_size
        self.final_model = DenseInternalModel(**kwargs)

    def fit(self, X: list, y):

        # # Fit each model on its corresponding dataset
        # for i, x in enumerate(X):
        #     self.ll_models[i].fit(x, np.argmax(y, axis=1))

        for i, x in enumerate(X):
            self.xg_models[i].fit(x, y)

        for i, x in enumerate(X):
            self.nn_models[i].fit(x, y)

        # Collect predictions from each model
        meta_features = []
        for i, x in enumerate(X):
            preds = self.ll_models[i].predict_proba(x)
            meta_features.append(preds)

        for i, x in enumerate(X):
            preds = self.xg_models[i].predict_proba(x)
            meta_features.append(preds)

        for i, x in enumerate(X):
            preds = self.nn_models[i].predict_proba(x)
            meta_features.append(preds)

        # Stack predictions horizontally (axis=1) to form the meta-features
        meta_features = np.hstack(meta_features)

        # Fit the final model on the meta-features
        self.final_model.fit(meta_features, y)  # Assuming y is the target for the final model

    def predict(self, X):

        # Collect predictions from each model
        meta_features = []
        # for i, x in enumerate(X):
        #     preds = self.ll_models[i].predict_proba(x)
        #     meta_features.append(preds)

        for i, x in enumerate(X):
            preds = self.xg_models[i].predict_proba(x)
            meta_features.append(preds)

        for i, x in enumerate(X):
            preds = self.nn_models[i].predict_proba(x)
            meta_features.append(preds)

        # Stack predictions horizontally (axis=1) to form the meta-features
        meta_features = np.hstack(meta_features)

        # Predict using the final model
        return self.final_model.predict(meta_features)



