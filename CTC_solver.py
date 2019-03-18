from keras.layers import *
from keras.models import *
from keras.utils import *
from keras.initializers import *
from keras.optimizers import *
import tensorflow as tf
import keras.backend as kback
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, MultiLabelBinarizer
import math
from matplotlib import pyplot as plt
import pandas as pd
import os
from keras.utils import to_categorical
import logging
import numpy as np

class lstm():


    def __init__(self, lrs, resume, start_epoch, epochs):

        self.lr = lrs
        self.resume = resume
        self.start_epoch = start_epoch
        self.epochs = epochs

        self.batch_size = 4  # Batch size for training.
        self.latent_dim = 16  # Latent dimensionality of the encoding space.

        self.log = logging.getLogger()
        self.log.setLevel(logging.DEBUG)

        letters = list('qwertyuiopasdfghjklzxcvbnm')
        letters.append('<GO>')
        letters.append('<EOS>')
        data = pd.read_csv('pool_layers.csv')
        words = data['word']

        le = LabelEncoder()
        le.fit(letters)
        self.target_vocab_to_int = dict(zip(le.classes_, le.transform(le.classes_)))
        self.int_to_vocab = dict(zip(le.transform(le.classes_), le.classes_))
        data['word'] = [le.transform(['<GO>'] + list(word) + ['<EOS>']) for word in words]

        self.target_vocab_size = len(self.target_vocab_to_int)

        train_signers = ['signer1', 'signer2', 'signer3', 'signer5']
        test_signers = ['signer4']

        self.loc_train = data.loc[data['signer'].isin(train_signers)]['filepath'].values
        self.dec_input_train = data.loc[data['signer'].isin(train_signers)]['word'].values

        self.loc_val = data.loc[data['signer'].isin(test_signers)]['filepath'].values
        self.dec_input_val = data.loc[data['signer'].isin(test_signers)]['word'].values

        both =  np.concatenate((self.dec_input_train, self.dec_input_val))

        target_lengths = [len(target) for target in both]
        self.max_seq_length = max(target_lengths)

        padded_train = np.zeros([len(self.dec_input_train), max(target_lengths)])
        padded_val = np.zeros([len(self.dec_input_val), max(target_lengths)])

        for word in range(len(self.dec_input_train)):
            padded_train[word, :len(self.dec_input_train[word])] = self.dec_input_train[word]

        for word in range(len(self.dec_input_val)):
                padded_val[word, :len(self.dec_input_val[word])] = self.dec_input_val[word]

        self.dec_input_train = to_categorical(padded_train, num_classes=self.target_vocab_size)

        self.dec_input_val = to_categorical(padded_val, num_classes=self.target_vocab_size)

    def get_pool_layers(self, locations):
        return [np.squeeze(np.load(location)) for location in locations]

    def format_videos(self, locations, yd, index):
        # shuffle indicies
        train_indicies = np.arange(locations.shape[0])
        np.random.shuffle(train_indicies)

        start_idx = (index * self.batch_size) % locations.shape[0]
        idx = train_indicies[start_idx:start_idx + self.batch_size]

        # create a feed dictionary for this batch
        videos = self.get_pool_layers(locations[idx])
        source_lengths = [video.shape[0] for video in videos]

        padded_videos = np.zeros([len(source_lengths), max(source_lengths), videos[0].shape[1]])

        for video in videos:
            padded_videos[:, :video.shape[0], :] = video

        padded_yd = yd[idx]

        actual_batch_size = padded_yd.shape[0]

        return padded_videos, padded_yd, actual_batch_size

    def ctc_lambda_func(args):
        y_pred, labels, input_length, label_length = args
        # the 2 is critical here since the first couple outputs of the RNN
        # tend to be garbage:
        y_pred = y_pred[:, 2:, :]
        return kback.ctc_batch_cost(labels, y_pred, input_length, label_length)

    def get_model(self):

        encoder_inputs = Input(shape=(None, 1024))
        model = Sequential()
        
        model.add(TimeDistributed(Dense(27, activation='softmax')))

        model.add(CuDNNLSTM(self.latent_dim, return_sequences=True))

        model.add(TimeDistributed(Dense(self.target_vocab_size, activation='softmax')))

        return model

    def decode_sequence(self, input_seq, model):

        # Encode the input as state vectors.
        states_value = encoder_model.predict(input_seq)

        # Generate empty target sequence of length 1.
        target_seq = np.zeros((1, 1, self.target_vocab_size))
        # Populate the first character of target sequence with the start character.
        target_seq[0, 0, self.target_vocab_to_int['<GO>']] = 1.
        
        predicted_seq = ""
        # Sampling loop for a batch of sequences
        # (to simplify, here we assume a batch of size 1).
        output_tokens = model.predict(input_seq)
        output_tokens = kback.get_value(kback.ctc_decode(out, input_length=output_tokens.shape[0],
                         greedy=True))[0]

            # Sample a token
        sampled_token_index = np.argmax(output_tokens, axis=1)
        for t in sampled_token_index:
            predicted_seq += self.int_to_vocab[sampled_token_index[t]]

        return predicted_seq


    def run_model(self, lr=None, print_every=100):


        val_losses = []
        overall_train_losses = []
        overall_val_losses = []


        if self.resume:
            #overall_train_losses = np.load(self.absolute_root + "/CNN/trained_networks/static_v2_lr-" + str(glr) + "/epoch-" + str(self.start_epoch) + "/static_v2_lr-" + str(glr) + "-overall_train_losses.npy").tolist()
            overall_train_losses = np.load("C:/Riley/DeepLetters/CNN/trained_networks/static_v2_lr-1e-06/epoch-" + str(self.start_epoch) + "/static_v2_lr-1e-06-overall_train_losses.npy").tolist()
            val_losses = np.load("C:/Riley/DeepLetters/CNN/trained_networks/static_v2_lr-1e-06/epoch-" + str(self.start_epoch) + "/static_v2_lr-1e-06-val_losses.npy").tolist()
            #val_losses = np.load(self.absolute_root + "/CNN/trained_networks/static_v2_lr-" + str(glr) + "/epoch-" + str(self.start_epoch) + "/static_v2_lr-" + str(glr) + "-val_losses.npy").tolist()

        iter_cnt = 0

        model = self.get_model()

        model.compile(optimizer=RMSprop(lr=lr, clipvalue=1), loss=ctc_lambda_func)

        model.summary(print_fn=self.log.info)
        for e in range(self.start_epoch, self.epochs):
            losses = []
            for i in range(int(math.ceil(self.loc_train.shape[0] / self.batch_size))):
                padded_videos, padded_yd, actual_batch_size = self.format_videos(locations=self.loc_train, yd=self.dec_input_train, index=i)

                decoder_target_data = np.append(padded_yd[:, 1:, :], np.zeros((padded_yd.shape[0], 1, 28)), axis=1)
                loss = model.train_on_batch([padded_videos, padded_yd], decoder_target_data)

                losses.append(loss * actual_batch_size)

                # if (iter_cnt % print_every) == 0:
                #     self.log.info("Iteration " + str(iter_cnt) + ": with minibatch training loss = " + str(loss))

                iter_cnt += 1
            epoch_loss = np.sum(losses) / self.loc_train.shape[0]
            overall_train_losses.append(epoch_loss)
            #val_confusion_matrix = np.sum(confusion_matricies) / Xd.shape[0]
            relative_root = "./CNN/trained_networks/LSTM-lr-" + str(lr) + "/epoch-" + str(e + 1)

            self.log.info("Epoch " + str(e + 1) + ", Overall loss = " + str(epoch_loss))

            self.log.info('Validation-------------------------')
            os.mkdir(relative_root)

            for i in range(int(math.ceil(self.loc_train.shape[0] / self.batch_size))):
                padded_videos, padded_yd, actual_batch_size = self.format_videos(locations=self.loc_val, yd=self.dec_input_val, index=i)
                decoder_target_data = np.append(padded_yd[:, 1:, :], np.zeros((padded_yd.shape[0], 1, 28)), axis=1)

                cur_val_loss = model.evaluate([padded_videos, padded_yd], decoder_target_data)
                if i%4 == 0:
                    ground_truth = [self.int_to_vocab[np.argmax(letter, axis=0)] for letter in padded_yd[0]]
                    self.log.info("Sample: " + str(self.decode_sequence(padded_videos[0].reshape(1,-1,1024), model)) + "Ground Truth: " + str(ground_truth))

                val_losses.append(cur_val_loss * actual_batch_size)

            val_epoch_loss = np.sum(val_losses) / self.loc_train.shape[0]
            overall_val_losses.append(val_epoch_loss)
            val_losses = []
            self.log.info("Validation, Overall loss = " + str(val_epoch_loss))
            # Save Model
            file = "./CNN/trained_networks/LSTM-lr-" + str(lr) + "/epoch-" + str(e + 1 - 5)
            if os.path.isdir(file):
                os.remove(file + '/train_model.h5')
                os.remove(file + '/encoder_model.h5')
                os.remove(file + '/decoder_model.h5')

            model.save(relative_root + "/train_model.h5")
            encoder_model.save(relative_root + "/encoder_model.h5")
            decoder_model.save(relative_root + "/decoder_model.h5")

            plt.plot(overall_train_losses)
            plt.grid(True)
            plt.title('Epoch {} Loss'.format(e + 1))
            plt.xlabel('Epoch number')
            plt.ylabel('Epoch Loss')

            np.save(relative_root + "/overall_train_losses.npy", overall_train_losses)
            plt.savefig(relative_root +"/TRAIN.png")

            plt.clf()
            plt.plot(overall_val_losses)
            plt.grid(True)
            plt.title('Epoch {} Loss'.format(e + 1))
            plt.xlabel('Validation run')
            plt.ylabel('Loss')

            np.save(relative_root + "/val_losses.npy", overall_val_losses)
            plt.savefig(relative_root +"/VAL.png")
            plt.clf()

            #val_confusion_matrix = pd.DataFrame(val_confusion_matrix, columns=classes, index=classes)
            #heatmap = sns.heatmap(val_confusion_matrix, annot=True).get_figure()
            #heatmap.savefig(relative_root +"/static_v2_lr-" + str(glr) + "-confusion_matrix.png")

        return overall_train_losses

    def train(self):
        lr = self.lr
        relative_root = "./CNN/trained_networks/LSTM-lr-" + str(lr)
        os.mkdir(relative_root)
        fileh = logging.FileHandler(relative_root + "/log.txt", "a+")
        fileh.setFormatter(logging.Formatter("%(asctime)-15s %(levelname)-8s %(message)s"))
        fileh.setLevel(logging.DEBUG)

        self.log.handlers = [fileh]
        self.run_model(lr)