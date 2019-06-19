'''
思想：
已有修复后的长传fixed_long.fasta和匹配信息matches.json
每个长串匹配了众多小串
长串做为A类点，小串作为B类点

B类点两两之间通过A类点计算偏置的众数和总连接数
最终每个B类点两两之间存在边，有总连接数，偏置众数和数量
以偏置众数为第一关键字，总连接数为第二关键字，求最小生成树？或生成链

众数边求最小生成树gg了
其他方法？

枚举每一条长串为起点，维护一个短串的集合和一个长串的集合，不断选择一个短串，将其匹配的所有长串拼合进来

直到不能进行，最后投票表决每个位置的字符。

短串用堆选dis最小的一个

正确性依赖于短串匹配到长串上错误率很低，可以确信短串一定匹配在长串上

data1 data2 效果太差了，如何优化？覆盖97，NGA50 9120略短

实际观察发现data1与data2都只输出了4种基因一共8条串

如何找出最后一条串？

1 对dis增加Threshold？

2 每次只拼合一个串？

3 还是以存在非常相似的短串为前提，长串拼接时对公共部分进行错误率检查？

本次尝试第二种想法 失败

尝试第三种想法 失败，只是把第4个串拆成了两半

那么只可能存在一种情况，有两个串非常地相似，或中间一段非常相似，无法区分，那么对dis增加阈值试试

失败。。

中间一段非常相似无法区分？

是否可以使用voter将其区分开来？

voter中存在两种十分数量相当的总数的值

尝试输出voter信息

失败，因为长串已经被短串修补过了，而且长串自身就有错误率

所以应当对matches进行一次修复：
多个短串匹配到一个长串，然而这些短串投票得到的值应当存在两个高峰，（data1短序列无误更是如此）
应当选择其中最高的一半认为是正确的，另一半不应当将短串匹配在这个长串上

但是实测，如果从一端开始选取匹配串，会对最终匹配结果造成影响，
因为前面可能删掉了某些串从而导致后面某个位置voter高峰值变化

'''
import argparse
import os
import Levenshtein as leve
from tqdm import tqdm
from collections import Counter
import json
import sys
import math
import heapq
import numpy as np
import heapq

sys.setrecursionlimit(90000)

DEFAULT_PARAM_FILE = 'param.json'
DEFAULT_LONG_FILE = 'long.fasta'
DEFAULT_SHORT_1_FILE = 'short_1.fasta'
DEFAULT_SHORT_2_FILE = 'short_2.fasta'
DEFAULT_FIXED_LONG_FILE = 'long_repair.fasta' # MatchesFixed
DEFAULT_MATCHES_FILE = 'matches_repair.json' # MatchesFixed
DEFAULT_ANS_FILE = 'v3contig_repair.fasta' # MatchesFixed

ARGS = None

MINDIS = 10

def parse_args():
    global ARGS
    parser = argparse.ArgumentParser()
    parser.add_argument('DATA_DIR', type=str, help='the dataset\'s directory')
    parser.add_argument('-a', '--ANS_FILE', type=str,
                        default=DEFAULT_ANS_FILE, help='ans data file\'s name')
    parser.add_argument('-fl', '--FIXED_LONG_FILE', type=str,
                        default=DEFAULT_FIXED_LONG_FILE, help='fixed long data file\'s name')
    parser.add_argument('-m', '--MATCHES_FILE', type=str,
                        default=DEFAULT_MATCHES_FILE, help='match info file \'s name')
    parser.add_argument('-p', '--PARAM_FILE', type=str,
                        default=DEFAULT_PARAM_FILE, help='the param file\'s name')
    parser.add_argument('-l', '--LONG_FILE', type=str,
                        default=DEFAULT_LONG_FILE, help='the long data file\'s name')
    parser.add_argument('-s1', '--SHORT_1_FILE', type=str,
                        default=DEFAULT_SHORT_1_FILE, help='the short_1 file\'s name')
    parser.add_argument('-s2', '--SHORT_2_FILE', type=str,
                        default=DEFAULT_SHORT_2_FILE, help='the short_2 file\'s name')
    ARGS = parser.parse_args()
    ARGS.PARAM_FILE = os.path.join(ARGS.DATA_DIR, ARGS.PARAM_FILE)
    ARGS.LONG_FILE = os.path.join(ARGS.DATA_DIR, ARGS.LONG_FILE)
    ARGS.SHORT_1_FILE = os.path.join(ARGS.DATA_DIR, ARGS.SHORT_1_FILE)
    ARGS.SHORT_2_FILE = os.path.join(ARGS.DATA_DIR, ARGS.SHORT_2_FILE)
    ARGS.FIXED_LONG_FILE = os.path.join(ARGS.DATA_DIR, ARGS.FIXED_LONG_FILE)
    ARGS.MATCHES_FILE = os.path.join(ARGS.DATA_DIR, ARGS.MATCHES_FILE)
    ARGS.ANS_FILE = os.path.join(ARGS.DATA_DIR, ARGS.ANS_FILE)


def prepare_fasta_data(filename):
    content = []
    print('Load data', filename)
    with open(filename, 'r') as f:
        lines = f.readlines()
        name = 'Unknown'
        for i, line in enumerate(tqdm(lines)):
            if (i & 1) == 0:
                name = line.strip('\n')
            else:
                content.append({'name': name, 's': line.strip('\n')})
    return content


def get_comp_rev_data(content):
    tran = {'A': 'T', 'T': 'A', 'G': 'C', 'C': 'G'}
    return [{
        'name': data['name']+'(comp_rev)',
        's': ''.join([tran[c] for c in data['s']][::-1])
    } for data in content]


def can_merge(A, B, off):
    res = ''
    if off < 0:
        A, B = B, A
        off = -off
    common = min(len(A)-off, len(B))
    # if common <= 100:  # Threshold
    #     return False
    error_rate = leve.hamming(A[off:off+common], B[:common])/common
    if error_rate > 0.2:  # Threshold
        return False
    return True


if __name__ == "__main__":
    # load ARGS
    parse_args()
    # load data

    fixed_dataset = prepare_fasta_data(ARGS.FIXED_LONG_FILE)
    match_infoset = {}
    with open(ARGS.MATCHES_FILE, 'r') as f:
        match_infoset = json.loads('['+f.read().strip('\n')[:-1]+']')

    # map_point
    name_to_Apoint = {}
    Apoint_to_name = []
    Apoint_to_data = fixed_dataset

    name_to_Bpoint = {}
    Bpoint_to_name = []
    Bpoint_to_data = []

    A_out_edges = []
    B_out_edges = []

    def get_id(short_name, short):
        sid = name_to_Bpoint.get(short_name, -1)
        if sid == -1:
            sid = len(Bpoint_to_name)
            name_to_Bpoint[short_name] = sid
            Bpoint_to_name.append(short_name)
            Bpoint_to_data.append({'name': short_name, 's': short})
            B_out_edges.append([])
        return sid

    def encode_edge(A, B, dis, pos):
        return (dis, pos, A, B)  # 以元组存储便于比较，dis为第一关键字，pos为第二关键字

    def decode_edge(edge):  # return A, B, dis, pos
        return edge[2], edge[3], edge[0], edge[1]

    def add_edge(A, B, dis, pos):
        edge = encode_edge(A, B, dis, pos)
        A_out_edges[A].append(edge)
        B_out_edges[B].append(edge)

    # generate A point
    print('Generate A point')
    for long_data in tqdm(fixed_dataset):
        name_to_Apoint[long_data['name']] = len(Apoint_to_name)
        Apoint_to_name.append(long_data['name'])
        A_out_edges.append([])

    total_A = len(Apoint_to_name)
    print('total A', total_A)

    # generate B point and add edges
    print('Generate B point and build graph')
    for i, match_info in enumerate(tqdm(match_infoset)):
        for match in match_info:
            short_name = match['name']
            short = match['s']
            sid = get_id(short_name, short)
            add_edge(i, sid, match['dis'], match['pos'])
    total_B = len(Bpoint_to_name)
    print('total B', total_B)

    # sort all out edges by distance
    for u in range(total_A):
        A_out_edges[u] = sorted(
            A_out_edges[u], key=lambda x: x[2])  # sort by dis

    for u in range(total_B):
        B_out_edges[u] = sorted(
            B_out_edges[u], key=lambda x: x[2])  # sort by dis

    print('Try directly connect')
    visited_A = np.zeros(total_A, dtype=bool)
    offset = np.zeros(total_A, dtype=int)
    ans = []
    for st in tqdm(range(total_A)):
        if visited_A[st]:
            continue
        now_A_set = []
        # now_B_set = []
        now_B_set = A_out_edges[st].copy()  # (dis, pos, A, B)
        heapq.heapify(now_B_set)
        visited_A[st] = True
        visited_B = np.zeros(total_B, dtype=bool)
        offset[st] = 0
        now_A_set.append((0, st))
        while len(now_B_set) > 0:
            edge = heapq.heappop(now_B_set)
            A, B, dis, pos = decode_edge(edge)
            # if dis >= MINDIS: # 为dis增加阈值
            #     continue
            if visited_B[B]:
                continue
            visited_B[B] = True
            for e_to_A in B_out_edges[B]:
                A2, _, dis2, pos2 = decode_edge(e_to_A)
                if visited_A[A2]:
                    continue
                # 对A与A2公共部分错误率设定阈值
                offset_A2_to_A = pos - pos2
                # if can_merge(Apoint_to_data[A]['s'],Apoint_to_data[A2]['s'],offset_A2_to_A) == False:
                #     continue
                visited_A[A2] = True
                offset[A2] = offset[A]+offset_A2_to_A
                now_A_set.append((offset[A2], A2))
                for e_to_B in A_out_edges[A2]:
                    if visited_B[e_to_B[3]] == False:  # B
                        heapq.heappush(now_B_set, e_to_B)
                # break # 只拼入一个长串 失败
        # vote
        now_A_set = sorted(now_A_set)  # sort by offset
        common_offset = now_A_set[0][0]
        now_A_set = [(x[0]-common_offset, x[1]) for x in now_A_set]
        # now_A_set = [map(lambda x: (x[0]-common_offset, x[1]), now_A_set)]
        length = now_A_set[-1][0]+1000  # this time length
        now_set = []
        p = 0
        res = ''
        # print('length', length)
        for i in range(length):
            while p < len(now_A_set) and now_A_set[p][0] <= i:
                now_set.append(now_A_set[p])
                p += 1
            while len(now_set) > 0 and now_set[0][0]+1000 <= i:
                now_set.pop(0)
            assert len(now_set) > 0
            voter = Counter()
            for off, A in now_set:
                voter.update(Apoint_to_data[A]['s'][i-off])
            res += voter.most_common(1)[0][0]

            # v3: voter check
            tops = voter.most_common(2)
            if len(tops) == 2 and tops[1][1] > 5: # Threshold
                if tops[1][1] / tops[0][1] > 0.4: # Threshold
                    print('Simular', tops)

        ans.append(res)

    ans = sorted(ans, key=lambda x: len(x), reverse=True)
    with open(ARGS.ANS_FILE, 'w') as f:
        for i, s in enumerate(ans):
            print('{:3d} length: {:d}'.format(i, len(s)))
            f.write('>ans_{0}/1\n{1}\n'.format(i, s))
