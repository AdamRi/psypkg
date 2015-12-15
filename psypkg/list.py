from __future__ import division
import sys

from .pkg import read_index


def human_size(size):
    if size < 2 ** 10:
        return str(size)

    elif size < 2 ** 20:
        size = "%.1f" % (size / 2 ** 10)
        unit = "K"

    elif size < 2 ** 30:
        size = "%.1f" % (size / 2 ** 20)
        unit = "M"

    elif size < 2 ** 40:
        size = "%.1f" % (size / 2 ** 30)
        unit = "G"

    elif size < 2 ** 50:
        size = "%.1f" % (size / 2 ** 40)
        unit = "T"

    elif size < 2 ** 60:
        size = "%.1f" % (size / 2 ** 50)
        unit = "P"

    elif size < 2 ** 70:
        size = "%.1f" % (size / 2 ** 60)
        unit = "E"

    elif size < 2 ** 80:
        size = "%.1f" % (size / 2 ** 70)
        unit = "Z"

    else:
        size = "%.1f" % (size / 2 ** 80)
        unit = "Y"

    if size.endswith(".0"):
        size = size[:-2]

    return size + unit


def print_list(stream, details=False, human=False, delim="\n", sort_func=None, out=sys.stdout):
    index = read_index(stream)

    if sort_func:
        index = sorted(index, cmp=sort_func)

    if details:
        if human:
            size_to_str = human_size
        else:
            size_to_str = str

        count = 0
        sum_size = 0
        out.write("    Offset       Size Name%s" % delim)
        for name, offset, size in index:
            out.write("%10u %10s %s%s" % (offset, size_to_str(size), name, delim))
            count += 1
            sum_size += size
        out.write("%d file(s) (%s) %s" % (count, size_to_str(sum_size), delim))
    else:
        for name, offset, size in index:
            out.write("%s%s" % (name, delim))