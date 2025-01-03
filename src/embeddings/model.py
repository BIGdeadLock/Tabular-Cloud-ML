import pandas as pd
from huggingface_hub.keras_mixin import keras
from keras.src.applications import resnet
from keras.src.applications.resnet import preprocess_input
from keras.src.layers import Dense, BatchNormalization
from keras.src import Sequential
from gensim.models import KeyedVectors
import numpy as np
import torch
import torch.nn as nn
import torchvision.transforms as transforms
import tensorflow as tf
from tab2img.converter import Tab2Img
from keras.src.callbacks import EarlyStopping
from keras.src.utils import to_categorical
from src.utils.helpers import create_image_from_numbers, expand_matrix_to_img_size
from src.utils.config import config
from src.utils.constansts import CPU_DEVICE, EMBEDDING_MODEL_PATH

class DNNEmbedding(nn.Module):

    name = "dnn_embedding"

    def __init__(self, **kwargs):
        super(DNNEmbedding, self).__init__()
        X, y = kwargs.get("X"), kwargs.get("y")
        dataset_name = kwargs.get("dataset_name", None)
        path = EMBEDDING_MODEL_PATH / f"{dataset_name}.h5" or ""
        if path.exists():
            model = keras.models.load_model(path)
        else:
            model = self._get_trained_model(X,y)
            model.save(path)

        self.model = model.layers[0]
        self.output_shape = (1, X.shape[1]//2)


    def forward(self, x):

        if type(x) is pd.DataFrame:
            x = x.to_numpy()

        embedding = self.model(x)
        return embedding



    def _get_trained_model(self, X:np.ndarray | pd.DataFrame, y:np.ndarray | pd.DataFrame):

        num_classes = len(set(y))
        y = to_categorical(y, num_classes)

        model = Sequential()
        model.add(Dense(units=X.shape[1] // 2, activation='relu', name="embedding"))
        model.add(BatchNormalization())
        model.add(Dense(units=num_classes, activation='softmax', name="output"))

        model.compile(loss='categorical_crossentropy', optimizer='adam', metrics=['accuracy'])
        early_stop = EarlyStopping(patience=2, monitor="loss")

        with tf.device(CPU_DEVICE):
            # Dense networks run faster on CPU
            model.fit(X, y, epochs=50, batch_size=64, callbacks=[early_stop])

        return model

class ImageEmbedding(nn.Module):

    name = "image_embedding"

    def __init__(self, **kwargs):

        super(ImageEmbedding, self).__init__()

        base_model = config.embedding_config.base_model
        # Load a pre-trained ResNet model
        if base_model == 'resnet50':
            self.model = resnet.ResNet50(weights="imagenet", include_top=False)
        elif base_model == 'resnet101':
            self.model = resnet.ResNet101(weights="imagenet", include_top=False)
        elif base_model == 'resnet152':
            self.model = resnet.ResNet152(weights="imagenet", include_top=False)
        else:
            raise ValueError("Unsupported ResNet model")

        self.input_shape = (224, 224)
        self.output_shape = (7, 7, 2048)
        self.image_transformer = Tab2Img()
        self.image_transformer.fit(kwargs.get("X").values, kwargs.get("y").values)


    def forward(self, x):
        if len(x.shape) == 3:
            x = x.reshape(1,224,224,3)
        # Extract embeddings

        image = self.image_transformer.transform(x) # expand from 6x6 to 224x224
        image = expand_matrix_to_img_size(image[0], self.input_shape)

        embeddings = self.model(preprocess_input(image))
        return embeddings.numpy()[0]


class w2vEmbedding(nn.Module):
    name = "w2v_embedding"

    def __init__(self, **kwargs):
        super(w2vEmbedding, self).__init__()
        model_path = ""
        # Load the pre-trained Word2Vec model
        self.model = KeyedVectors.load_word2vec_format(model_path, binary=True)
        self.vector_size = self.model.vector_size

    def embed_word(self, word):
        # Get the embedding for a single word
        if word in self.model:
            return self.model[word]
        else:
            # Return a zero vector if the word is not in the vocabulary
            return np.zeros(self.vector_size)

    def forward(self, words):
        # Get embeddings for a list of words
        embeddings = [self.embed_word(word) for word in words]
        return np.stack(embeddings, axis=0)


class NumericalTableEmbeddings(nn.Module):

    name = "numerical_table_embedding"

    def __init__(self, **kwargs):
        super(NumericalTableEmbeddings, self).__init__()
        # Load pre-trained ResNet model and remove the final classification layer
        self.resnet = resnet.ResNet101(weights='imagenet', include_top=False, pooling='avg')
        # self.resnet = nn.Sequential(*list(resnet_model.children())[:-1])  # Remove the last FC layer
        self.image_size = kwargs.get('image_size', (224, 224))
        self.font_size = kwargs.get('font_size', 80)
        self.output_shape = (config.experiment_config.n_noise_samples, 1, 2048)

        # Image transformation pipeline
        self.transform = transforms.Compose([
            transforms.Resize(self.image_size),  # ResNet expects 224x224 images
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            # Normalization like ResNet expects
        ])

    # Function to pass an image through ResNet and get the embedding
    def get_embedding_from_image(self, img):
        array = np.array(img)[np.newaxis, ...] # Add batch dim
        with torch.no_grad():
            embedding = self.resnet(array)  # Get 1D embedding
        return embedding.cpu().numpy()

    # Function to get the row embedding by averaging all column embeddings
    def get_row_embedding(self, row):
        # embeddings = []

        # for value in row:
        #     value = int(value) # Round to make the image more clear
        #     img = create_image_from_number(value, image_size=self.image_size, font_size=self.font_size)
        #     embedding = self.get_embedding_from_image(img)
        #     embeddings.append(embedding)
        #
        # # Stack embeddings and compute the mean
        # embeddings = torch.stack(embeddings)

        row = row.astype(np.int16)
        image = create_image_from_numbers(row)

        embedding = self.get_embedding_from_image(image)

        return embedding

        # return torch.mean(embeddings, dim=0)



    # Function to process an entire dataframe and return row embeddings
    def forward(self, matrix):

        if type(matrix) is pd.DataFrame:
            matrix = matrix.to_numpy()

        row_embeddings = []
        for row in matrix:
            row_embedding = self.get_row_embedding(row)
            row_embeddings.append(row_embedding)
        # Convert to tensor
        return np.stack(row_embeddings)


