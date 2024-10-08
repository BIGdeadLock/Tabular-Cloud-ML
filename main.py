# import azure_authentication_client
# azure_authentication_client.patch_http_headers()


import yaml
import src.utils.constansts as consts
from src.experiments.handler import ExperimentHandler
from src.experiments.k_fold_handler import KFoldExperimentHandler
import pandas as pd
import os
import tensorflow as tf
import numpy as np

np.random.seed(42)

def main():

    with open(consts.CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)

    # Use GPU only when using Decon
    if config['ENCRYPTOR']['name'] not in consts.GPU_MODELS:
        # Hide GPU from visible devices
        tf.config.set_visible_devices([], 'GPU')

    if config["EXPERIMENT"]["k_fold"] == 1:
        experiment_handler = ExperimentHandler(config)
    else:
        experiment_handler = KFoldExperimentHandler(config)
    new_report_lines = experiment_handler.run_experiment()
    report = pd.DataFrame()

    if os.path.exists(consts.REPORT_PATH):
        report = pd.read_csv(consts.REPORT_PATH, index_col="Unnamed: 0")

    report = pd.concat([report, new_report_lines], ignore_index=True)

    print(f"Saving report to {consts.REPORT_PATH}")
    report.to_csv(consts.REPORT_PATH)

if __name__ == '__main__':
    main()