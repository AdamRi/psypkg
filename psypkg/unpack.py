import os

from psypkg import read_index

# for Python < 3.3 and Windows
def highlevel_sendfile(outfile, infile, offset, size):
    infile.seek(offset, 0)
    while size > 0:
        if size > 2 ** 20:
            chunk_size = 2 ** 20
        else:
            chunk_size = size
        size -= chunk_size
        data = infile.read(chunk_size)
        outfile.write(data)
        if len(data) < chunk_size:
            raise IOError("unexpected end of file")


if hasattr(os, 'sendfile'):
    def sendfile(outfile, infile, offset, size):
        try:
            out_fd = outfile.fileno()
            in_fd = infile.fileno()
        except:
            highlevel_sendfile(outfile, infile, offset, size)
        else:
            # size == 0 has special meaning for some sendfile implentations
            if size > 0:
                os.sendfile(out_fd, in_fd, offset, size)
else:
    sendfile = highlevel_sendfile

def shall_unpack(paths, name):
    path = name.split(os.path.sep)
    for i in range(1, len(path) + 1):
        prefix = os.path.join(*path[0:i])
        if prefix in paths:
            return True
    return False


def unpack_files(stream, files, outdir=".", callback=lambda name: None):
    for name, offset, size in read_index(stream):
        if shall_unpack(files, name):
            unpack_file(stream, name, offset, size, outdir, callback)


def unpack_file(stream, name, offset, size, outdir=".", callback=lambda name: None):
    prefix, name = os.path.split(name)
    prefix = os.path.join(outdir, prefix)
    if not os.path.exists(prefix):
        os.makedirs(prefix)
    name = os.path.join(prefix, name)
    callback(name)
    with open(name, "wb") as fp:
        sendfile(fp, stream, offset, size)


def unpack(stream, outdir=".", callback=lambda name: None):
    for name, offset, size in read_index(stream):
        unpack_file(stream, name, offset, size, outdir, callback)