import torch
from torchtext import data
import time
from torchtext.data import Field, Dataset, BucketIterator, TabularDataset
from torchtext.data import Field, BucketIterator, TabularDataset
from torchtext import datasets
import torchtext
import random
import pandas as pd
from sklearn.model_selection import train_test_split
import torch.nn as nn
import torch.optim as optim

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
path = '/home/mehrpad/Desktop/dl_seminar/seminar_code'
SEED = 1234
batch_size = 16
num_epoch = 10

torch.manual_seed(SEED)
torch.backends.cudnn.deterministic = True

TEXT = data.Field(tokenize='spacy', include_lengths=True) # For saving the lenth of sentenses
LABEL = data.LabelField(dtype=torch.float)


class RNN(nn.Module):
    def __init__(self, vocab_size, embedding_dim, hidden_dim, output_dim, n_layers,
                 bidirectional, dropout, pad_idx):
        super().__init__()

        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=pad_idx)

        self.rnn = nn.LSTM(embedding_dim,
                           hidden_dim,
                           num_layers=n_layers,
                           bidirectional=bidirectional,
                           dropout=dropout)

        self.fc = nn.Linear(hidden_dim * 2, output_dim)

        self.dropout = nn.Dropout(dropout)

    def forward(self, text, text_lengths):
        # text = [sent len, batch size]

        embedded = self.dropout(self.embedding(text))

        # embedded = [sent len, batch size, emb dim]

        # pack sequence
        packed_embedded = nn.utils.rnn.pack_padded_sequence(embedded, text_lengths)

        packed_output, (hidden, cell) = self.rnn(packed_embedded)

        # unpack sequence
        output, output_lengths = nn.utils.rnn.pad_packed_sequence(packed_output)

        # output = [sent len, batch size, hid dim * num directions]
        # output over padding tokens are zero tensors

        # hidden = [num layers * num directions, batch size, hid dim]
        # cell = [num layers * num directions, batch size, hid dim]

        # concat the final forward (hidden[-2,:,:]) and backward (hidden[-1,:,:]) hidden layers
        # and apply dropout

        hidden = self.dropout(torch.cat((hidden[-2, :, :], hidden[-1, :, :]), dim=1))

        # hidden = [batch size, hid dim * num directions]

        return self.fc(hidden)


def data_load():

    data = (open(path + '/data/dataset_SemEval/message_level/train/2014_b_train.txt').read().split("\n"))
    data = data[:len(data) - 1]
    data_test = (open(path + '/data/dataset_SemEval/message_level/train/2014_b_dev.txt').read().split("\n"))
    data_test = data[:len(data_test) - 1]

    ds = [(d.split("\t")[0], d.split("\t")[1], d.split("\t")[2], d.split("\t")[3]) for d in data if
          len(d.split("\t")) > 2]
    ds_test = [(d.split("\t")[0], d.split("\t")[1], d.split("\t")[2], d.split("\t")[3]) for d in data_test if
               len(d.split("\t")) > 2]

    ds_dic = {'id': [seq[0] for seq in ds], 'user_id': [seq[1] for seq in ds],
              'label': [seq[2] for seq in ds], 'text': [seq[3] for seq in ds]}
    ds_test_dic = {'id': [seq[0] for seq in ds_test], 'user_id': [seq[1] for seq in ds_test],
                   'label': [seq[2] for seq in ds_test], 'text': [seq[3] for seq in ds_test]}

    train_total = pd.DataFrame(ds_dic, columns=["id", "user_id", "text", "label"])
    train, val = train_test_split(train_total, test_size=0.2)
    test = pd.DataFrame(ds_test_dic, columns=["id", "user_id", "text", "label"])

    train.to_csv(path + "/data/dataset_SemEval/message_level/pre_data/train.csv", index=False)
    val.to_csv(path + "/data/dataset_SemEval/message_level/pre_data/val.csv", index=False)
    test.to_csv(path + "/data/dataset_SemEval/message_level/pre_data/test.csv", index=False)

    fields = [('id', None), ('user_id', None), ('text', TEXT), ('label', LABEL)]

    train_dataset, val_dataset = TabularDataset.splits(path=path + '/data/dataset_SemEval/message_level/pre_data',
                                                       train='train.csv',
                                                       validation='val.csv', format='csv', skip_header=True,
                                                       fields=fields)
    test_dataset = TabularDataset(path=path + '/data/dataset_SemEval/message_level/pre_data/test.csv',
                                  format='csv', skip_header=True, fields=fields)

    print(vars(train_dataset.examples[0]))
    print(vars(val_dataset.examples[-1]))
    print(f'Number of training examples: {len(train_dataset)}')
    print(f'Number of validation examples: {len(val_dataset)}')
    print(f'Number of testing examples: {len(test_dataset)}')

    MAX_VOCAB_SIZE = 25_000

    TEXT.build_vocab(train_dataset,
                     max_size=MAX_VOCAB_SIZE,
                     vectors="glove.6B.100d",
                     unk_init=torch.Tensor.normal_)

    LABEL.build_vocab(train_dataset)

    text_vocab_size = len(TEXT.vocab)
    print(f"Unique tokens in TEXT vocabulary: {len(TEXT.vocab)}")
    print(f"Unique tokens in LABEL vocabulary: {len(LABEL.vocab)}")


    train_data_iter = BucketIterator(train_dataset, batch_size=batch_size, train=True, sort_within_batch=True,
                                     sort_key=lambda x: len(x.text), device=device
                                     )
    valid_data_iter = BucketIterator(val_dataset, batch_size=batch_size, train=True, sort_within_batch=True,
                                     sort_key=lambda x: len(x.text), device=device
                                     )
    test_data_iter = BucketIterator(test_dataset, batch_size=batch_size, sort_within_batch=True,
                                     sort_key=lambda x: len(x.text), device=device, train=False)


    return train_data_iter, valid_data_iter, test_data_iter, text_vocab_size


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def binary_accuracy(preds, y):
    """
    Returns accuracy per batch, i.e. if you get 8/10 right, this returns 0.8, NOT 8
    """
    # round predictions to the closest integer
    rounded_preds = torch.round(torch.sigmoid(preds))
    correct = (rounded_preds == y).float()  # convert into float for division
    acc = correct.sum() / len(correct)
    return acc


def train(model, iterator, optimizer, criterion):
    epoch_loss = 0
    epoch_acc = 0

    model.train()

    for batch in iterator:
        optimizer.zero_grad()

        text, text_lengths = batch.text

        predictions = model(text, text_lengths).squeeze(1)

        loss = criterion(predictions, batch.label)

        acc = binary_accuracy(predictions, batch.label)

        loss.backward()

        optimizer.step()

        epoch_loss += loss.item()
        epoch_acc += acc.item()

    return epoch_loss / len(iterator), epoch_acc / len(iterator)


def evaluate(model, iterator, criterion):
    epoch_loss = 0
    epoch_acc = 0

    model.eval()

    with torch.no_grad():
        for batch in iterator:
            text, text_lengths = batch.text

            predictions = model(text, text_lengths).squeeze(1)

            loss = criterion(predictions, batch.label)

            acc = binary_accuracy(predictions, batch.label)

            epoch_loss += loss.item()
            epoch_acc += acc.item()

    return epoch_loss / len(iterator), epoch_acc / len(iterator)


def test_model(model, test_data_iter, criterion ):

    model.load_state_dict(torch.load('tut2-model.pt'))

    test_loss, test_acc = evaluate(model, test_data_iter, criterion)

    print(f'Test Loss: {test_loss:.3f} | Test Acc: {test_acc * 100:.2f}%')

def epoch_time(start_time, end_time):
    elapsed_time = end_time - start_time
    elapsed_mins = int(elapsed_time / 60)
    elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
    return elapsed_mins, elapsed_secs


# create model
train_data_iter, valid_data_iter, test_data_iter, text_vocab_size = data_load()

INPUT_DIM = text_vocab_size
EMBEDDING_DIM = 100
HIDDEN_DIM = 256
OUTPUT_DIM = 1
N_LAYERS = 2
BIDIRECTIONAL = True
DROPOUT = 0.5
PAD_IDX = TEXT.vocab.stoi[TEXT.pad_token]

model = RNN(INPUT_DIM,
            EMBEDDING_DIM,
            HIDDEN_DIM,
            OUTPUT_DIM,
            N_LAYERS,
            BIDIRECTIONAL,
            DROPOUT,
            PAD_IDX)

print(f'The model has {count_parameters(model):,} trainable parameters')

pretrained_embeddings = TEXT.vocab.vectors

print(pretrained_embeddings.shape)

UNK_IDX = TEXT.vocab.stoi[TEXT.unk_token]

model.embedding.weight.data[UNK_IDX] = torch.zeros(EMBEDDING_DIM)
model.embedding.weight.data[PAD_IDX] = torch.zeros(EMBEDDING_DIM)

print(model.embedding.weight.data)


optimizer = optim.Adam(model.parameters())
criterion = nn.BCEWithLogitsLoss()

model = model.to(device)
criterion = criterion.to(device)

best_valid_loss = float('inf')

for epoch in range(num_epoch):

    start_time = time.time()

    train_loss, train_acc = train(model, train_data_iter, optimizer, criterion)
    valid_loss, valid_acc = evaluate(model, valid_data_iter, criterion)

    end_time = time.time()

    epoch_mins, epoch_secs = epoch_time(start_time, end_time)

    if valid_loss < best_valid_loss:
        best_valid_loss = valid_loss
        torch.save(model.state_dict(), path + '/nlp/model/nlp2-model.pt')

    print(f'Epoch: {epoch + 1:02} | Epoch Time: {epoch_mins}m {epoch_secs}s')
    print(f'\tTrain Loss: {train_loss:.3f} | Train Acc: {train_acc * 100:.2f}%')
    print(f'\t Val. Loss: {valid_loss:.3f} |  Val. Acc: {valid_acc * 100:.2f}%')