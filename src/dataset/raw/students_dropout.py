from src.utils.helpers import preprocess
import pandas as pd
from src.dataset.raw.base import DATASET_DIR, RawDataset

class StudentsDropout(RawDataset):
    name = 'students_dropout'

    def __init__(self, **kwargs):

        super().__init__(**kwargs)
        DATASET_PATH = DATASET_DIR / StudentsDropout.name /  f"dataset.csv"
        dataset = pd.read_csv(DATASET_PATH)
        self.X, self.y = self._preprocess(dataset)
        self.cloud_models = kwargs.get("cloud_models")
        self.name = StudentsDropout.name

    def _preprocess(self, dataset):
        X, y = dataset.iloc[:, :-1], dataset.iloc[:, -1]
        y = y.astype(int)
        return preprocess(X, cloud_dataset=True), y

