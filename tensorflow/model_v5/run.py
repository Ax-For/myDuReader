# -*- coding:utf8 -*-
# ==============================================================================
# Copyright 2017 Baidu.com, Inc. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""
This module prepares and runs the whole system.
"""
import sys
if sys.version[0] == '2':
    reload(sys)
    sys.setdefaultencoding("utf-8")
sys.path.append('..')
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import pickle
import argparse
import logging
from dataset import BRCDataset
from vocab import Vocab
from rc_model import RCModel
import json
#两个model：BIDAF for QA & YESNO for YESNO classification
#其中的BIDAF为baseline基础上glove预训练词向量、self-matching层、 shared normalization计算loss
#YESNO模型，输入为问题和answer，self-matching后，对answer的表示做max-pooling然后接全连接层做三分类

def parse_args():
    """
    Parses command line arguments.
    """
    parser = argparse.ArgumentParser('Reading Comprehension on BaiduRC dataset')
    parser.add_argument('--prepare', action='store_true',
                        help='create the directories, prepare the vocabulary and embeddings')
    parser.add_argument('--train', action='store_true',
                        help='train the model')
    parser.add_argument('--evaluate', action='store_true',
                        help='evaluate the model on dev set')
    parser.add_argument('--predict', action='store_true',
                        help='predict the answers for test set with trained model')
    parser.add_argument('--gpu', type=str, default='0',
                        help='specify gpu device')

    train_settings = parser.add_argument_group('train settings')
    train_settings.add_argument('--optim', default='adam',
                                help='optimizer type')
    train_settings.add_argument('--learning_rate', type=float, default=0.001,
                                help='learning rate')
    train_settings.add_argument('--weight_decay', type=float, default=0,
                                help='weight decay')
    train_settings.add_argument('--dropout_keep_prob', type=float, default=1,#
                                help='dropout keep rate')
    train_settings.add_argument('--batch_size', type=int, default=32,
                                help='train batch size')
    train_settings.add_argument('--epochs', type=int, default=10,
                                help='train epochs')
    train_settings.add_argument('--restore', action='store_true',
                                help='restore the training')

    model_settings = parser.add_argument_group('model settings')
    model_settings.add_argument('--algo', choices=['BIDAF', 'YESNO'], default='BIDAF',
                                help='choose the algorithm to use')
    model_settings.add_argument('--embed_size', type=int, default=300,
                                help='size of the embeddings')
    model_settings.add_argument('--hidden_size', type=int, default=150,
                                help='size of LSTM hidden units')
    model_settings.add_argument('--max_p_num', type=int, default=5,
                                help='max passage num in one sample')
    model_settings.add_argument('--max_p_len', type=int, default=500,
                                help='max length of passage')
    model_settings.add_argument('--max_q_len', type=int, default=60,
                                help='max length of question')
    model_settings.add_argument('--max_a_len', type=int, default=300,#TODO 200——>300
                                help='max length of answer')

    path_settings = parser.add_argument_group('path settings')
    path_settings.add_argument('--train_files', nargs='+',
                               default=['../../data/preprocessed/trainset_v1/search.train.json', '../../data/preprocessed/trainset_v1/zhidao.train.json'],
                               help='list of files that contain the preprocessed train data')
    path_settings.add_argument('--dev_files', nargs='+',
                               default=['../../data/preprocessed/devset_v1/search.dev.json','../../data/preprocessed/devset_v1/zhidao.dev.json'],
                               help='list of files that contain the preprocessed dev data')
    # testset for QA task
    # path_settings.add_argument('--test_files', nargs='+',
    #                            default=['../../data/preprocessed/testset_v1/search.test.json','../../data/preprocessed/testset_v1/zhidao.test.json','../../data/preprocessed/testset_v2/search.test.json','../../data/preprocessed/testset_v2/zhidao.test.json'],
    #                            help='list of files that contain the preprocessed test data')
    # path_settings.add_argument('--test_files', nargs='+',
    #                            default=['../../out/06/results/test.predicted.v2.json'],
    #                            help='list of files that contain the preprocessed test data')
    
    # testset for YESNO task
    #TODO！---修改YESNO模型的输入
    #QA模型的预测结果作为YESNO模型的输入，为其中的YESNO类问题进一步预测YESNO label
    path_settings.add_argument('--test_files', nargs='+',
                               default=['../../out/1352/results/test.predicted.gml_top8.json'],
                               help='list of files that contain the preprocessed test data')

    path_settings.add_argument('--brc_dir', default='../../data/baidu',
                               help='the dir with preprocessed baidu reading comprehension data')
    
    path_settings.add_argument('--embedding_path', default='../../data/glove/vectors.txt',#TODO!!
                               help='the path to save vocabulary')
    path_settings.add_argument('--vocab_path', default='../../data/vocab/full.glove.vocab.data',#TODO!!
                               help='the path to save vocabulary')

    path_settings.add_argument('--run_id', default='7', help='Run ID [0]')#已训好的YESNO模型
    
    args=parser.parse_args()
    # path_settings.add_argument('--vocab_dir', default='../../data/vocab/',
    #                            help='the dir to save vocabulary')
    # path_settings.add_argument('--model_dir', default='../../data/models/',
    #                            help='the dir to store models')
    # path_settings.add_argument('--result_dir', default='../../data/results/',
    #                            help='the dir to output the results')
    # path_settings.add_argument('--summary_dir', default='../../data/summary/',
    #                            help='the dir to write tensorboard summary')
    # path_settings.add_argument('--log_path',
    #                            help='path of the log file. If not set, logs are printed to console')
    
    #根据run_id指定目录
    args.model_dir = '../../out/{}/models/'.format(str(args.run_id).zfill(2))
    args.result_dir = '../../out/{}/results/'.format(str(args.run_id).zfill(2))
    args.summary_dir = '../../out/{}/summary/'.format(str(args.run_id).zfill(2))
    args.log_path = '../../out/{}/log.log'.format(str(args.run_id).zfill(2))
    
    # return parser.parse_args()
    return args


def prepare(args):
    """
    checks data, creates the directories, prepare the vocabulary and embeddings
    """
    logger = logging.getLogger("brc")
    logger.info('Checking the data files...')
    for data_path in args.train_files + args.dev_files + args.test_files:
        assert os.path.exists(data_path), '{} file does not exist.'.format(data_path)
    
    logger.info('Preparing the directories...')
    
    logger.info('Building vocabulary...')
    brc_data = BRCDataset(args.algo, args.max_p_num, args.max_p_len, args.max_q_len, args.max_a_len,
                          args.train_files, args.dev_files, args.test_files)
    vocab = Vocab(lower=True)
    for word in brc_data.word_iter('train'):#构建词典只包含训练集
        vocab.add(word)

    unfiltered_vocab_size = vocab.size()
    vocab.filter_tokens_by_cnt(min_cnt=2)
    filtered_num = unfiltered_vocab_size - vocab.size()
    logger.info('After filter {} tokens, the final vocab size is {}'.format(filtered_num,
                                                                            vocab.size()))

    logger.info('Assigning embeddings...')
    # vocab.randomly_init_embeddings(args.embed_size)#TODO-load_pretrained_embeddings
    vocab.load_pretrained_embeddings(args.embedding_path)#glove pre-trained

    logger.info('Saving vocab...')
    # with open(os.path.join(args.vocab_dir, 'vocab.data'), 'wb') as fout:
    with open(args.vocab_path, 'wb') as fout:#不区分search&zhidao
        pickle.dump(vocab, fout)

    logger.info('Done with preparing!')


def train(args):
    """
    trains the reading comprehension model
    """
    logger = logging.getLogger("brc")
    logger.info('Load data_set and vocab...')
    # with open(os.path.join(args.vocab_dir, 'vocab.data'), 'rb') as fin:
    with open(args.vocab_path, 'rb') as fin:
        vocab = pickle.load(fin)
    brc_data = BRCDataset(args.algo, args.max_p_num, args.max_p_len, args.max_q_len, args.max_a_len,
                          args.train_files, args.dev_files)
    logger.info('Converting text into ids...')

    brc_data.convert_to_ids(vocab)
    
    logger.info('Initialize the model...')
    rc_model = RCModel(vocab, args)
    if args.restore:
        logger.info('Restoring the model...')
        rc_model.restore(model_dir=args.model_dir, model_prefix=args.algo)
    logger.info('Training the model...')
    rc_model.train(brc_data, args.epochs, args.batch_size, save_dir=args.model_dir,
                   save_prefix=args.algo, dropout_keep_prob=args.dropout_keep_prob)
    logger.info('Done with model training!')


def evaluate(args):
    """
    evaluate the trained model on dev files
    """
    logger = logging.getLogger("brc")
    logger.info('Load data_set and vocab...')
    # with open(os.path.join(args.vocab_dir, 'vocab.data'), 'rb') as fin:
    with open(args.vocab_path, 'rb') as fin:
        vocab = pickle.load(fin)
    assert len(args.dev_files) > 0, 'No dev files are provided.'
    brc_data = BRCDataset(args.algo, args.max_p_num, args.max_p_len, args.max_q_len, args.max_a_len, dev_files=args.dev_files)
    logger.info('Converting text into ids...')
    
    brc_data.convert_to_ids(vocab)

    logger.info('Restoring the model...')
    rc_model = RCModel(vocab, args)
    rc_model.restore(model_dir=args.model_dir, model_prefix=args.algo)
    logger.info('Evaluating the model on dev set...')
    dev_batches = brc_data.gen_mini_batches('dev', args.batch_size,
                                            pad_id=vocab.get_id(vocab.pad_token), shuffle=False)
    dev_loss, dev_bleu_rouge = rc_model.evaluate(
        dev_batches, result_dir=args.result_dir, result_prefix='dev.predicted')
    logger.info('Loss on dev set: {}'.format(dev_loss))
    logger.info('Result on dev set: {}'.format(dev_bleu_rouge))
    logger.info('Predicted answers are saved to {}'.format(os.path.join(args.result_dir)))


def predict(args):
    """
    predicts answers for test files
    """
    logger = logging.getLogger("brc")
    logger.info('Load data_set and vocab...')
    with open(args.vocab_path, 'rb') as fin:
        vocab = pickle.load(fin)
    assert len(args.test_files) > 0, 'No test files are provided.'
    brc_data = BRCDataset(args.algo, args.max_p_num, args.max_p_len, args.max_q_len, args.max_a_len,
                          test_files=args.test_files)
    logger.info('Converting text into ids...')
    
    brc_data.convert_to_ids(vocab)
    
    logger.info('Restoring the model...')
    rc_model = RCModel(vocab, args)
    rc_model.restore(model_dir=args.model_dir, model_prefix=args.algo)
    logger.info('Predicting answers for test set...')
    test_batches = brc_data.gen_mini_batches('test', args.batch_size,
                                             pad_id=vocab.get_id(vocab.pad_token), shuffle=False)
    if args.algo=='YESNO':
        qa_resultPath=args.test_files[0]#只会有一个文件！
        (filepath, tempfilename) = os.path.split(qa_resultPath)
        (qarst_filename, extension) = os.path.splitext(tempfilename)
        result_prefix=qarst_filename
    else:
        result_prefix='test.predicted.qa'

    rc_model.evaluate(test_batches,
                      result_dir=args.result_dir, result_prefix=result_prefix)
    if args.algo=='YESNO':#将YESNO结果合并入QA结果
        qa_resultPath=args.test_files[0]#只会有一个文件！
        yesno_resultPath= args.result_dir+'/'+result_prefix+'.YESNO.json'
        out_file_path=args.result_dir+'/'+result_prefix+'.134.class.'+str(args.run_id)+'.json'

        #首先载入YESNO部分的预测结果
        yesno_records={}
        with open(yesno_resultPath,'r') as f_in:
            for line in f_in:
                sample = json.loads(line)
                yesno_records[sample['question_id']]=line

        total_rst_num=0
        with open(qa_resultPath,'r') as f_in:
            with open(out_file_path, 'w') as f_out:
                for line in f_in:
                    total_rst_num+=1
                    sample = json.loads(line)
                    if sample['question_id'] in yesno_records:
                        line=yesno_records[sample['question_id']]
                    f_out.write(line)

        print('total rst num : ',total_rst_num)
        print('yes no label combining done!')

def run():
    """
    Prepares and runs the whole system.
    """
    args = parse_args()
    for dir_path in [os.path.dirname(args.vocab_path), os.path.dirname(args.log_path), args.model_dir, args.result_dir]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    ############定义一个logger，既能输出到文件又能控制台
    logger = logging.getLogger("brc")#? baidu reading comprehension
    logger.setLevel(logging.INFO)
    
    fh = logging.FileHandler(args.log_path, mode="a")#TODO
    fh.setLevel(logging.INFO)
    #输出到控制台
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    #制定formatter
    fmt = "%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s"
    datefmt = "%a %Y-%m-%d %H:%M:%S" #TODO month
    formatter = logging.Formatter(fmt, datefmt)

    #为文件和控制台设置输出格式
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    #添加两种句柄到logger对象
    logger.addHandler(fh)
    logger.addHandler(ch)
    #########################logger end############################

    logger.info('Running with args : {}'.format(args))

    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu

    if args.prepare:
        prepare(args)
    if args.train:
        train(args)
    if args.evaluate:
        evaluate(args)
    if args.predict:
        predict(args)

if __name__ == '__main__':
    run()
