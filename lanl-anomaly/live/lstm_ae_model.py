"""LSTMAutoencoder for live recon error computation.

Clean copy of the model class from src/05_lstm_autoencoder.py.
Only the model definition — no training code, no argparse.
"""
import torch.nn as nn


class LSTMAutoencoder(nn.Module):
    def __init__(self, vocab_size, hidden_dim=128, num_layers=2):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.vocab_size = vocab_size
        self.embed = nn.Embedding(vocab_size, hidden_dim)
        self.encoder = nn.LSTM(hidden_dim, hidden_dim, num_layers=num_layers,
                               batch_first=True)
        self.decoder = nn.LSTM(hidden_dim, hidden_dim, num_layers=num_layers,
                               batch_first=True)
        self.output_proj = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x):
        embedded = self.embed(x)
        _, (hidden, cell) = self.encoder(embedded)
        decoder_output, _ = self.decoder(embedded, (hidden, cell))
        logits = self.output_proj(decoder_output)
        return logits

    def encode(self, x):
        embedded = self.embed(x)
        _, (hidden, cell) = self.encoder(embedded)
        return hidden[-1]
