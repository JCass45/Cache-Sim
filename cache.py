#!/usr/bin/python3

import subprocess
from math import log2
from pprint import pprint


class Cache():
    def __init__(self, l: int, k: int, n: int):
        # L bytes/line, K directories, N sets
        self.sets = [[None for _ in range(k)] for _ in range(n)]
        self.directories = [
            [[False for _ in range(l // 4)] for _ in range(k)] for _ in range(n)]

        self.tag_mask, self.set_mask, self.offset = self.calc_masks(l, n)
        self.set_shift = log2(l)
        self.tag_shift = log2(n) + self.set_shift

    def calc_masks(self, l, n):
        offset = log2(l)
        set_num = log2(n)
        tag = 27 - offset - set_num
        offset_mask = int((27 - offset) * '0' + offset * '1')
        set_mask = int((27 - set_num) * '0' + set_num * '1' + offset * '0')
        tag_mask = int(tag * '1' + (set_num + offset) * '0')
        return tag_mask, set_mask, offset_mask


def main():
    instruction_cache = Cache(16, 1, 1024)
    data_cache = Cache(16, 8, 256)
    trace = read_trace()
    pprint(data_cache.directories)


def read_trace():
    raw_trace = subprocess.run(
        args=['xxd', '-b', '-l', '500', 'gcc1.trace'],
        stdout=subprocess.PIPE
    ).stdout.decode().split('\n')

    # List of lists containing 6 bytes each
    split_trace = [row.split(' ')[1: 7] for row in raw_trace if row != '']

    # Flattened list of lists
    flat_trace = ''
    for s in [item for sublist in split_trace for item in sublist]:
        flat_trace += s

    # Separate into 32 bit segments, leaving out every 2nd 32 bit segment
    trace = []
    for i in range(0, len(flat_trace), 64):
        trace.append(int(flat_trace[i:i + 32], 2))

    return trace


def analyse(trace, ir_cache, d_cache):
    burst_mask = int('00011000000000000000000000000000', 2)
    burst_shift = 27
    access_mask = int('11100000000000000000000000000000')
    access_shift = 29
    address_mask = int('00000000011111111111111111111111', 2)
    access_lookup = {
        4: 'IR',
        6: 'DR',
        7: 'DW'
    }

    for mem in trace:
        access_type = access_lookup.get((mem & access_mask) >> access_shift)
        if access_type == 'IR':
            ir_cache.read()
        elif access_type == 'DR':
            ir_cache.read()
        elif access_type == 'DW':
            ir_cache.write()
        else:
            print('Non cache-related access type')


if __name__ == '__main__':
    main()
