import numpy as np
from keras.api.models import load_model
import os

from src.utils.constansts import ENCRYPTOR_MODEL_FILE_PATH

class BaseEncryptor:

    name: str

    def __init__(self, input_shape=None, output_shape=None):
        self.model = None
        self.output_shape = output_shape
        self.input_shape = input_shape

    def build_generator(self, input_shape, output_shape):
        raise NotImplementedError("Subclasses should implement this method")

    def save_model(self, filename):
        if self.model is not None:
            self.model.save(filename)  # For Keras models
            # For Scikit-learn models, use joblib.dump(self.model, filename)

    def load_model(self, filename):
        self.model = load_model(filename)  # For Keras models

    def encode(self, inputs) -> np.array:

        if self.model is None:
            if os.path.exists(ENCRYPTOR_MODEL_FILE_PATH):
                self.model = load_model(ENCRYPTOR_MODEL_FILE_PATH)
            else:
                input_shape = inputs.shape[1:]
                output_shape = self.output_shape or (1, inputs.shape[2])
                self.model = self.build_generator(input_shape, output_shape)
                self.save_model(ENCRYPTOR_MODEL_FILE_PATH)

        return self.model(inputs).numpy()


class Encryptors:
    """
    Ensemble class to join together numerous encryptors from the same type.
    """
    name: str

    def __init__(self, input_shape=None, output_shape=None, number_of_encryptors_to_init=1, enc_base_cls=BaseEncryptor):
        self.input_shape = input_shape
        self.output_shape = output_shape
        self.number_of_encryptors_to_init = number_of_encryptors_to_init
        self.models = None
        self.enc_base_cls = enc_base_cls
        self.name =  enc_base_cls.name

    def encode(self, inputs, number_of_encoder_to_use=1) -> np.array:
        if self.models is None:
            self.models = [self.enc_base_cls(output_shape=self.output_shape) for _ in range(self.number_of_encryptors_to_init)]

        assert number_of_encoder_to_use <= len(self.models), \
            f"Error: number_of_encoder_to_use ({number_of_encoder_to_use}) exceeds the number of available models ({len(self.models)})"

        outputs = []
        for encoder in self.models[:number_of_encoder_to_use]:
            outputs.append(encoder.encode(inputs))

        return np.vstack(outputs)
