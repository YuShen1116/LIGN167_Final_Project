#!/usr/bin/env python
#-*- coding:utf-8 -*-
# author:Darksoul
# datetime:11/24/2018 22:02
# software: PyCharm

from network import *

from torch import optim
from torch.nn.utils import clip_grad_norm_
from random import randint
from tqdm import tqdm
# import loss func
import masked_cross_entropy
import numpy as np


def nmt_training(src, tgt, pairs, test_src, test_tgt, test_pairs):
    num_batch = len(pairs) // cfg.batch_size

    encoder_test = Encoder(src.num, cfg.embed_size, cfg.hidden_size, cfg.n_layers_encoder, dropout=cfg.dropout)
    decoder_test = Decoder(cfg.embed_size, cfg.hidden_size, tgt.num, cfg.n_layers_decoder, dropout=cfg.dropout)

    net = Seq2Seq(encoder_test,decoder_test).cuda()
    net = load_checkpoint(net, cfg)

    opt = optim.Adam(net.parameters(), cfg.lr)

    total_loss = []

    for step in range(1, cfg.iteration-cfg.load_checkpoint):
        tmp_loss = 0

        for batch_index in range(num_batch):


            input_batches, input_lengths, \
            target_batches, target_lengths = random_batch(src, tgt, pairs, cfg.batch_size, batch_index)
            opt.zero_grad()
            output = net(input_batches, input_lengths, target_batches, target_lengths)

            # mask loss
            if cfg.loss_type == 'mask':
                loss = masked_cross_entropy.compute_loss(
                    output.transpose(0, 1).contiguous(),
                    target_batches.transpose(0, 1).contiguous(),
                    target_lengths, ignore_index=cfg.PAD_idx
                )
            else:
                loss = F.nll_loss(output[1:].view(-1, tgt.num),
                                  target_batches[1:].contiguous().view(-1),
                                  ignore_index=cfg.PAD_idx)
            tmp_loss += loss.item()
            total_loss.append(loss.item())

            clip_grad_norm_(net.parameters(), cfg.grad_clip)
            loss.backward()
            opt.step()

        if (step + cfg.load_checkpoint) % cfg.save_iteration == 0:
            test_idx = randint(0, cfg.batch_size-1)
            with open('./loss_log_train.txt', 'w') as outfile:
                for item in total_loss:
                    outfile.write("%s\n" % item)

            print("Epoch: {}, Loss: {}".format(step + cfg.load_checkpoint, tmp_loss/num_batch))
            save_checkpoint(net, cfg, step + cfg.load_checkpoint)

            _, pred = net.inference(input_batches[:, test_idx].reshape(input_lengths[0].item(), 1),
                                    input_lengths[0].reshape(1))

            try:
                inp = ' '.join([src.idx2w[t] for t in input_batches[:,test_idx].cpu().numpy() if t != PAD_idx])
                pred = ' '.join([tgt.idx2w[t] for t in pred if t != PAD_idx])
                gt = ' '.join([tgt.idx2w[t] for t in target_batches[:,test_idx].cpu().numpy() if t != PAD_idx])
                print("Input: {}".format(inp))
                print("Ground Truth: {}".format(gt))
                print("Prediction: {}".format(pred))
            except Exception as e:
                print(e)

        # print("Epoch {} finished".format(str(step)))
        random.shuffle(pairs)


def nmt_testing(src, tgt, pairs, test_src, test_tgt, test_pairs):

    encoder_test = Encoder(src.num, cfg.embed_size, cfg.hidden_size, cfg.n_layers_encoder, dropout=cfg.dropout)
    decoder_test = Decoder(cfg.embed_size, cfg.hidden_size, tgt.num, cfg.n_layers_decoder, dropout=cfg.dropout)


    net = Seq2Seq(encoder_test,decoder_test).cuda()
    net = BeamSearch(net.encoder, net.decoder, cfg.beam_widths).cuda()
    net = load_checkpoint(net, cfg)

    # if don't want beam search, set beam width = [1]
    for i in cfg.beam_widths:
        blue_score = []
        for index_sample in tqdm(range(len(test_pairs))):
            input_batches, input_lengths, \
            target_batches, target_lengths = random_batch(test_src, test_tgt, test_pairs, 1, index_sample)

            for test_idx in range(1):
                pred = net(input_batches[:, test_idx].reshape(input_lengths[0].item(), 1), input_lengths[0].reshape(1),
                           i, MAX_LENGTH)
                inp = ' '.join([test_src.idx2w[t] for t in input_batches[:, test_idx].cpu().numpy()])
                mt = ' '.join([test_tgt.idx2w[t] for t in pred if t != PAD_idx])
                idx = mt.find('<eos>')
                mt = mt[:idx + 5]
                ref = ' '.join([test_tgt.idx2w[t] for t in target_batches[:, test_idx].cpu().numpy() if t != PAD_idx])
                blue_score.append(bleu([mt], [[ref]], 4))

            if index_sample % 100 == 0:
                print(str(index_sample))
        #         print('INPUT:\n' + inp)
        #         print('REF:\n' + ref)
        #         print('PREDICTION:\n' + mt)
        #         print("------")
        print(str(i) + " finished: " + str(np.mean(blue_score)))


if __name__ == '__main__':
    if not os.path.exists(cfg.checkpoints_path):
        os.mkdir(cfg.checkpoints_path)

    src, tgt, pairs = prepareData(cfg.data_path, 'english', 'chinese')
    src.trim()
    tgt.trim()

    test_src, test_tgt, test_pairs = prepareData('data/small_set/test.txt', 'english', 'chinese')
    test_src.trim()
    test_tgt.trim()

    if cfg.is_training:
        nmt_training(src, tgt, pairs, test_src, test_tgt, test_pairs)
    else:
        nmt_testing(src, tgt, pairs, test_src, test_tgt, test_pairs)

