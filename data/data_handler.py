"""
@authors:
Soroosh Tayebi Arasteh <soroosh.arasteh@fau.de>
Mehrpad Monajem <mehrpad.monajem@fau.de>
"""

import numpy as np
import random
import torch
from torchtext import data
from Train_Test_Valid import Mode
from configs.serde import read_config
import os
import pandas as pd
import pdb



class data_provider_V2():
    '''
    Packed padded sequences
    Pre-trained embedding: glove.6B.100d
    Tokenizer: spacy
    '''
    def __init__(self, cfg_path, batch_size=1, split_ratio=0.8, max_vocab_size=25000, mode=Mode.TRAIN, seed=1):
        '''
        Args:
            cfg_path (string):
                Config file path of the experiment
            max_vocab_size (int):
                The number of unique words in our training set is usually over 100,000,
                which means that our one-hot vectors will have over 100,000 dimensions! SLOW TRAINIG!
                We only take the top max_vocab_size most common words.
            split_ratio (float):
                train-valid splitting
            mode (enumeration Mode):
                Nature of operation to be done with the data.
                Possible inputs are Mode.PREDICTION, Mode.TRAIN, Mode.VALID, Mode.TEST
                Default value: Mode.TRAIN
        '''
        params = read_config(cfg_path)
        self.cfg_path = cfg_path
        self.mode = mode
        self.seed = seed
        self.split_ratio = split_ratio
        self.max_vocab_size = max_vocab_size
        self.dataset_path = params['input_data_path']
        self.train_file_name = params['train_file_name']
        self.test_file_name = params['test_file_name']
        self.data_format = params['data_format']
        self.pretrained_embedding = params['pretrained_embedding']
        self.tokenizer = params['tokenizer']
        self.batch_size = batch_size


    def data_loader(self):
        '''
        :include_lengths: Packed padded sequences: will make our RNN only process the non-padded elements of our sequence,
            and for any padded element the `output` will be a zero tensor.
            Note: padding is done by adding <pad> (not zero!)
        :tokenize: the "tokenization" (the act of splitting the string into discrete "tokens") should be done using the spaCy tokenizer.
        '''
        '''Packed padded sequences'''
        TEXT = data.Field(tokenize=self.tokenizer, include_lengths=True)  # For saving the length of sentences
        LABEL = data.LabelField()

        fields = [('id', None), ('user_id', None),  ('label', LABEL), ('text', TEXT)]
        train_data, test_data = data.TabularDataset.splits(
            path=self.dataset_path,
            train=self.train_file_name,
            test=self.test_file_name,
            format=self.data_format,
            fields=fields,
            skip_header=False)

        # validation data
        train_data, valid_data = train_data.split(random_state=random.seed(self.seed), split_ratio=self.split_ratio)

        # create the vocabulary only on the training set!!!
        # vectors: instead of having our word embeddings initialized randomly, they are initialized with these pre-trained vectors.
        # initialize words in your vocabulary but not in your pre-trained embeddings to Gaussian
        TEXT.build_vocab(train_data, max_size=self.max_vocab_size,
                         vectors=self.pretrained_embedding, unk_init=torch.Tensor.normal_)
        LABEL.build_vocab(train_data)

        labels = LABEL.vocab.itos
        vocab_idx = TEXT.vocab.stoi

        vocab_size = len(TEXT.vocab)
        pretrained_embeddings = TEXT.vocab.vectors

        # the indices of the padding token <pad> and <unk> in the vocabulary
        PAD_IDX = TEXT.vocab.stoi[TEXT.pad_token]
        UNK_IDX = TEXT.vocab.stoi[TEXT.unk_token]
        # What do we do with words that appear in examples but we have cut from the vocabulary?
        # We replace them with a special unknown or <unk> token.


        # for packed padded sequences all of the tensors within a batch need to be sorted by their lengths
        train_iterator, valid_iterator, test_iterator = data.BucketIterator.splits((
            train_data, valid_data, test_data), batch_size=self.batch_size,
            sort_within_batch=True, sort_key=lambda x: len(x.text))
        if self.mode == Mode.TEST:
            return test_iterator, vocab_size, PAD_IDX, UNK_IDX, pretrained_embeddings
        elif self.mode == Mode.PREDICTION:
            return labels, vocab_idx, vocab_size, PAD_IDX, UNK_IDX, pretrained_embeddings
        else:
            return train_iterator, valid_iterator, vocab_size, PAD_IDX, UNK_IDX, pretrained_embeddings


class data_provider_PostReply():
    '''
    Packed padded sequences
    Pre-trained embedding: glove.6B.100d
    Tokenizer: spacy
    '''
    def __init__(self, cfg_path, batch_size=1, split_ratio=0.8, max_vocab_size=25000, mode=Mode.TRAIN, seed=1):
        '''
        Args:
            cfg_path (string):
                Config file path of the experiment
            max_vocab_size (int):
                The number of unique words in our training set is usually over 100,000,
                which means that our one-hot vectors will have over 100,000 dimensions! SLOW TRAINIG!
                We only take the top max_vocab_size most common words.
            split_ratio (float):
                train-valid splitting
            mode (enumeration Mode):
                Nature of operation to be done with the data.
                Possible inputs are Mode.PREDICTION, Mode.TRAIN, Mode.VALID, Mode.TEST
                Default value: Mode.TRAIN
        '''
        params = read_config(cfg_path)
        self.cfg_path = cfg_path
        self.mode = mode
        self.seed = seed
        self.split_ratio = split_ratio
        self.max_vocab_size = max_vocab_size
        self.dataset_path = params['postreply_data_path']
        self.train_file_name = params['reply_with_max_label_file_name']
        self.data_format = params['reply_data_format']
        self.pretrained_embedding = params['pretrained_embedding']
        self.tokenizer = params['tokenizer']
        self.batch_size = batch_size


    def data_loader(self):
        '''
        :include_lengths: Packed padded sequences: will make our RNN only process the non-padded elements of our sequence,
            and for any padded element the `output` will be a zero tensor.
            Note: padding is done by adding <pad> (not zero!)
        :tokenize: the "tokenization" (the act of splitting the string into discrete "tokens") should be done using the spaCy tokenizer.
        '''
        '''Packed padded sequences'''
        TEXT = data.Field(tokenize=self.tokenizer, include_lengths=True)  # For saving the length of sentences
        LABEL = data.LabelField()

        fields = [('label', LABEL), ('text', TEXT)]
        train_data = data.TabularDataset(
            path=os.path.join(self.dataset_path, self.train_file_name),
            format=self.data_format,
            fields=fields,
            skip_header=True)

        # validation data
        train_data, valid_data = train_data.split(random_state=random.seed(self.seed), split_ratio=self.split_ratio)

        # create the vocabulary only on the training set!!!
        # vectors: instead of having our word embeddings initialized randomly, they are initialized with these pre-trained vectors.
        # initialize words in your vocabulary but not in your pre-trained embeddings to Gaussian
        TEXT.build_vocab(train_data, max_size=self.max_vocab_size,
                         vectors=self.pretrained_embedding, unk_init=torch.Tensor.normal_)
        LABEL.build_vocab(train_data)

        labels = LABEL.vocab.itos
        vocab_idx = TEXT.vocab.stoi

        vocab_size = len(TEXT.vocab)
        pretrained_embeddings = TEXT.vocab.vectors

        # the indices of the padding token <pad> and <unk> in the vocabulary
        PAD_IDX = TEXT.vocab.stoi[TEXT.pad_token]
        UNK_IDX = TEXT.vocab.stoi[TEXT.unk_token]
        # What do we do with words that appear in examples but we have cut from the vocabulary?
        # We replace them with a special unknown or <unk> token.


        # for packed padded sequences all of the tensors within a batch need to be sorted by their lengths
        train_iterator, valid_iterator = data.BucketIterator.splits((
            train_data, valid_data), batch_size=self.batch_size,
            sort_within_batch=True, sort_key=lambda x: len(x.text))

        test_iterator = None

        if self.mode == Mode.TEST:
            return test_iterator, vocab_size, PAD_IDX, UNK_IDX, pretrained_embeddings
        elif self.mode == Mode.PREDICTION:
            return labels, vocab_idx, vocab_size, PAD_IDX, UNK_IDX, pretrained_embeddings
        else:
            return train_iterator, valid_iterator, vocab_size, PAD_IDX, UNK_IDX, pretrained_embeddings


def summarizer(data_path, input_file_name, output_file_name):
    data = pd.read_csv(os.path.join(data_path, input_file_name))
    data_new = data.drop(['id', 'user', 'reply'], axis=1)
    data_final = pd.DataFrame(columns=['label', 'tweet'])
    it = iter(range(0, len(data_new)))
    for tweet in it:

        id = tweet
        label_pos = 0
        label_neg = 0
        label_nat = 0
        label = data_new.iloc[tweet][0]
        tweet_text = data_new.iloc[tweet][1]

        if label == 'positive':
            label_pos += 1
        elif label == 'negative':
            label_neg += 1
        elif label == 'neutral':
            label_nat += 1

        while True:
            tweet = next(it)
            if tweet_text == data_new.iloc[tweet][1]:
                if data_new.iloc[tweet][0] == 'positive':
                    label_pos += 1
                elif data_new.iloc[tweet][0] == 'negative':
                    label_neg += 1
                elif data_new.iloc[tweet][0] == 'neutral':
                    label_nat += 1
            else:
                break
            if tweet + 1 >= len(data_new):
                break
        var = {label_pos: "positive", label_neg: "negative", label_nat: "neutral"}
        label_final = var.get(max(var))

        df = pd.DataFrame([[label_final, tweet_text]], columns=['label', 'tweet'])
        data_final = data_final.append(df)

    data_final.to_csv(os.path.join(data_path, output_file_name), index=False)


def post_reply_downloader(list_of_word, max_num_tweets, mode='download'):
    path = '/home/mehrpad/Desktop/dl_seminar/git_seminar/data/preprocessing_utils/GetOldTweets3-0.0.10'
    max_tweets = max_num_tweets
    list_word = list_of_word
    for word in list_word:
        print('The word is:', word,'- Max number of tweets:', max_tweets)
        os.system('python %s/GetOldTweets3.py --querysearch "%s" --lang en --toptweets --maxtweets %s'
                      ' --output=%s/%s.csv' %(path, word, max_tweets, path, word))
    if mode == 'test':
        data = pd.read_csv('%s/%s.csv' % (path, list_word[0]))
        return data



if __name__=='__main__':
    CONFIG_PATH = '/home/mehrpad/Desktop/dl_seminar/git_seminar/configs/config.json'
    data_handler = data_provider_PostReply(cfg_path=CONFIG_PATH, batch_size=1, split_ratio=0.8, max_vocab_size=25000)
    train_iterator, valid_iterator, vocab_size, PAD_IDX, UNK_IDX, pretrained_embeddings = data_handler.data_loader()
    # pdb.set_trace()
    # a=2