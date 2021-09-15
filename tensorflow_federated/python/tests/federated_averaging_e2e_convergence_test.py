# Copyright 2018, The TensorFlow Federated Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""End-to-end convergence tests for the FedAvg algorithm on realistic data."""

from absl.testing import parameterized
import numpy as np
import tensorflow as tf
import tensorflow_federated as tff


def _get_tff_optimizer(learning_rate=0.1):
  return tff.learning.optimizers.build_sgdm(learning_rate=learning_rate)


def _get_keras_optimizer_fn(learning_rate=0.1):
  return lambda: tf.keras.optimizers.SGD(learning_rate=learning_rate)


class FederatedAveragingE2ETest(tff.test.TestCase, parameterized.TestCase):

  @parameterized.named_parameters([
      ('keras_opt', _get_keras_optimizer_fn()),
      ('tff_opt', _get_tff_optimizer()),
  ])
  def test_emnist10_cnn_convergence(self, client_optimizer_fn):
    train_client_spec = tff.simulation.baselines.ClientSpec(
        num_epochs=1, batch_size=32, shuffle_buffer_size=1)
    task = tff.simulation.baselines.emnist.create_character_recognition_task(
        train_client_spec, model_id='cnn', only_digits=True)
    train_client_ids = sorted(task.datasets.train_data.client_ids)
    preprocessed_train_data = task.datasets.train_data.preprocess(
        task.datasets.train_preprocess_fn)

    def client_selection_fn(round_num):
      random_state = np.random.RandomState(round_num)
      return random_state.choice(train_client_ids, size=10, replace=False)

    process = tff.learning.build_federated_averaging_process(
        model_fn=task.model_fn, client_optimizer_fn=client_optimizer_fn)
    state = process.initialize()
    training_metrics = []
    for round_num in range(200):
      selected_clients = client_selection_fn(round_num)
      client_data = [
          preprocessed_train_data.create_tf_dataset_for_client(a)
          for a in selected_clients
      ]
      state, metrics = process.next(state, client_data)
      training_metrics.append(metrics['train'])

    loss_last_10_rounds = [a['loss'] for a in training_metrics[-10:]]
    accuracy_last_10_rounds = [
        a['sparse_categorical_accuracy'] for a in training_metrics[-10:]
    ]
    average_loss_last_10_rounds = np.mean(loss_last_10_rounds)
    average_accuracy_last_10_rounds = np.mean(accuracy_last_10_rounds)

    self.assertLessEqual(average_loss_last_10_rounds, 0.15)
    self.assertGreater(average_accuracy_last_10_rounds, 0.95)


if __name__ == '__main__':
  # We must use the test execution context for the secure intrinsics introduced
  # by tff.learning.secure_aggregator.
  tff.backends.test.set_test_execution_context()
  tff.test.main()
