#!/usr/bin/python3

import subprocess
from math import log2
from collections import deque
from time import time
from pprint import pprint

# Set for reduced number of address from trace file
DEBUG = False


class Cache:
    def __init__(self, l: int, k: int, n: int):
        # N sets, K lines wide
        self.sets = [[None for _ in range(k)] for _ in range(n)]
        self.lru_queue = [deque() for _ in range(n)]

        # For each set(N), K lines that are L bytes wide
        self.dirs = [[[False for _ in range(l)]
                      for _ in range(k)] for _ in range(n)]

        self.tag_mask, self.set_mask, self.offset_mask = self.calc_masks(l, n)
        self.set_shift = int(log2(l))
        self.tag_shift = int(log2(n) + self.set_shift)

        self.hits = 0
        self.misses = 0
        self.dr_accesses = 0
        self.dw_accesses = 0

    def calc_masks(self, l, n):
        offset = int(log2(l))
        set_num = int(log2(n))
        tag = 27 - offset - set_num

        offset_mask = int((27 - offset) * '0' + offset * '1', 2)
        set_mask = int((27 - set_num) * '0' + set_num * '1' + offset * '0', 2)
        tag_mask = int(tag * '1' + (set_num + offset) * '0', 2)

        return tag_mask, set_mask, offset_mask

    def read(self, address, burst_count):
        self.dr_accesses += 1 + burst_count

        offset = (address & self.offset_mask)
        set_num = (address & self.set_mask) >> self.set_shift
        tag = (address & self.tag_mask) >> self.tag_shift

        if tag not in self.sets[set_num]:
            self.tag_miss(tag, set_num, offset)
        else:
            tag_index = self.sets[set_num].index(tag)
            if not self.dirs[set_num][tag_index][offset]:
                self.offset_miss(set_num, tag_index, offset)
                self.hits += burst_count
                self.misses += 1
            else:
                self.lru_reshuffle(set_num, tag)
                self.hits += 1 + burst_count

    def write(self, address, burst_count):
        self.dw_accesses += 1 + burst_count

        offset = (address & self.offset_mask)
        set_num = (address & self.set_mask) >> self.set_shift
        tag = (address & self.tag_mask) >> self.tag_shift

        if tag not in self.sets[set_num]:
            self.tag_miss(tag, set_num, offset)
            self.hits += burst_count
            self.misses += 1
        else:
            tag_index = self.sets[set_num].index(tag)
            self.dirs[set_num][tag_index][offset] = True
            self.lru_reshuffle(set_num, tag)
            self.hits += 1 + burst_count

    def tag_miss(self, tag, set_num, offset):
        '''
        This method is called when a tag is not existent in a set.
        If there is room to spare in the set, the tag will be added, otherwise
        the LRU policy will be called
        '''

        try:
            new_tag_index = self.sets[set_num].index(None)
        except ValueError:
            # Pop the LRU tag from the queue
            evicted_tag = self.lru_queue[set_num].popleft()
            evicted_tag_index = self.sets[set_num].index(evicted_tag)
            new_tag_index = evicted_tag_index
        finally:
            # Insert the new tag into the cache line
            self.sets[set_num][new_tag_index] = tag
            # Here we would go to MM and get the data
            self.dirs[set_num][new_tag_index][offset] = True
            self.lru_queue[set_num].append(tag)

    def offset_miss(self, set_num, tag_index, offset):
        '''
        This method is called when a tag is resident in a set, but
        the offset into it's directory entry is empty.

        We simulate a read from main memory by setting the position to True
        '''

        self.dirs[set_num][tag_index][offset] = True
        self.misses += 1

    def lru_reshuffle(self, set_num, tag):
        '''
        This method is called whenever a cache line has been accessed
        and it is no longer the LRU value

        The LRU Queue keeps the LRU item at the front of the queue
        '''

        try:
            self.lru_queue[set_num].remove(tag)
        except ValueError:
            print('Unexpected: Tag was not in lru queue')
        finally:
            self.lru_queue[set_num].append(tag)

    def print_results(self):
        print('Total Accesses: {}'.format(self.dr_accesses + self.dw_accesses))
        print('Read Accesses: {}'.format(self.dr_accesses))
        print('Write Accesses: {}'.format(self.dw_accesses))
        print('Hits: {}'.format(self.hits))
        print('Misses: {}'.format(self.misses))
        print(
            'Hit Rate: {:.2f}%'.format(
                self.hits / (self.dr_accesses + self.dw_accesses) * 100)
        )


def main():
    instruction_cache = Cache(16, 1, 1024)
    data_cache = Cache(16, 8, 256)
    trace = read_trace()

    start = time()
    analyse(trace, instruction_cache, data_cache)
    end = time()

    print('Execution time: {}ms'.format((end - start) * 1000))
    print("---Instruction Cache---")
    instruction_cache.print_results()
    print('---Data Cache---')
    data_cache.print_results()


def read_trace():
    if DEBUG:
        args = ['xxd', '-b', '-c', '4', '-l', '10000', 'gcc1.trace']
    else:
        args = ['xxd', '-b', '-c', '4', 'gcc1.trace']

    raw_trace = subprocess.run(
        args=args,
        stdout=subprocess.PIPE
    ).stdout.decode().split('\n')

    # List of lists containing 4 bytes each
    split_trace = [row.split(' ')[1: 5] for row in raw_trace if row != '']

    trace = []
    for i in range(0, len(split_trace), 2):
        s = ''
        for byte in split_trace[i]:
            s += byte
        trace.append(int(s, 2))

    return trace


def analyse(trace, ir_cache, d_cache):
    burst_mask = int('00011000000000000000000000000000', 2)
    burst_shift = 27
    access_mask = int('11100000000000000000000000000000', 2)
    access_shift = 29
    address_mask = int('00000000011111111111111111111111', 2)
    access_lookup = {
        4: 'IR',
        6: 'DR',
        7: 'DW'
    }

    for mem in trace:
        access_type = access_lookup.get((mem & access_mask) >> access_shift)
        if access_type:
            address = mem & address_mask
            burst_count = (mem & burst_mask) >> burst_shift

            if access_type == 'IR':
                ir_cache.read(address, burst_count)
            elif access_type == 'DR':
                d_cache.read(address, burst_count)
            elif access_type == 'DW':
                d_cache.write(address, burst_count)
            else:
                raise ValueError(
                    'Unexpected: Access-type not None, but still invalid')


if __name__ == '__main__':
    main()
