from tqdm import tqdm

from src.pipeline.no_stacking_encoding_pipeline import NoStackingFeatureEngineeringPipeline as FeatureEngineeringPipeline
from src.cloud import CloudModel, CLOUD_MODELS
from src.encryptor.base import Encryptors
from src.encryptor import EncryptorFactory
from src.internal_model.base import InternalInferenceModelFactory
from src.embeddings import EmbeddingsFactory
from src.utils.db import RawSplitDBFactory
from src.dataset import DatasetFactory, RawDataset
from src.utils.config import config
from loguru import logger
from src.experiments.base import ExperimentHandler


class NoStackingExperimentHandler(ExperimentHandler):

    def __init__(self):
        super().__init__("no_stacking_multiple_clouds")

    def run_experiment(self):

        assert len(config.cloud_config.names) >= 1

        if type(self.n_pred_vectors) is int:
            self.n_pred_vectors = [self.n_pred_vectors]

        datasets = config.dataset_config.names

        cloud_models: list[CloudModel] = [CLOUD_MODELS[name]() for name in config.cloud_config.names]


        for dataset_name in tqdm(datasets, total=len(datasets), desc="Datasets Progress", unit="dataset"):
            raw_dataset: RawDataset = DatasetFactory().get_dataset(dataset_name)


            embedding_model = EmbeddingsFactory().get_model(X=raw_dataset.X, y=raw_dataset.y, dataset_name=dataset_name)
            encryptor = Encryptors(dataset_name=dataset_name,
                                   output_shape=cloud_models[0].input_shape,
                                   number_of_encryptors_to_init=config.experiment_config.n_pred_vectors,
                                   enc_base_cls=EncryptorFactory.get_model_cls()
                                   )

            X_train, X_test, X_sample, y_train, y_test, y_sample = RawSplitDBFactory.get_db(raw_dataset).get_split()
            logger.debug(f"SAMPLE_SIZE {X_sample.shape}, TRAIN_SIZE: {X_train.shape}, TEST_SIZE: {X_test.shape}")

            logger.debug("#### GETTING RAW BASELINE PREDICTION ####")
            raw_baseline_acc, raw_baseline_f1 = raw_dataset.get_baseline(X_sample, X_test, y_sample, y_test)

            for n_pred_vectors in self.n_pred_vectors:

                logger.debug(f"CREATING THE CLOUD-TRAINSET FROM {dataset_name},"
                      f" WITH {n_pred_vectors} PREDICTION VECTORS")

                dataset_creator = FeatureEngineeringPipeline(
                    dataset_name=dataset_name,
                    encryptor=encryptor,
                    embeddings_model=embedding_model,
                    n_pred_vectors=n_pred_vectors,
                    metadata=raw_dataset.metadata
                )
                dataset, emb_baseline_dataset, pred_baseline_dataset, = dataset_creator.create(X_sample, y_sample, X_test, y_test)
                logger.debug("Finished Creating the dataset")


                # Log size for the final report
                train_shape = X_sample.shape
                test_shape = X_test.shape
                del X_test, X_sample, y_test, y_sample

                logger.info(f"############# USING {config.iim_config.name} FOR ALL BASELINES #############")
                baseline_emb_acc, baseline_emb_f1 = self.get_embedding_baseline(raw_dataset, emb_baseline_dataset)
                del emb_baseline_dataset # Free up memory

                baseline_pred_acc, baseline_pred_f1 = self.get_prediction_baseline(raw_dataset, pred_baseline_dataset)
                del pred_baseline_dataset # Free up memory

                logger.debug(f"#### EVALUATING INTERNAL MODEL ####\nDataset Shape: Train - {dataset.train.features.shape}, Test: {dataset.test.features.shape}")
                internal_model = InternalInferenceModelFactory().get_model(
                    num_classes=raw_dataset.get_n_classes(),
                    input_shape=dataset.train.features.shape[1],
                    type=config.iim_config.name[0]
                )
                internal_model.fit(
                    X=dataset.train.features, y=dataset.train.labels,
                )
                test_acc, test_f1 = internal_model.evaluate(
                    X=dataset.test.features, y=dataset.test.labels
                )

                self.log_results(
                    raw_dataset.name, train_shape, test_shape,
                    str([cloud_model for cloud_model in config.cloud_config.names]),
                    raw_baseline_acc, raw_baseline_f1,
                    baseline_emb_acc, baseline_emb_f1,
                    baseline_pred_acc, baseline_pred_f1,
                    test_acc, test_f1,
                    internal_model.name
                )

            del dataset # Free up space


        return self.report
