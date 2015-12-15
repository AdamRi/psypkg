import os
import struct


def read_index(stream):
    header = stream.read(8 * 4)

    magic, version, data_offset, records_count, dirs_offset, dirs_size, names_offset, types_offset = \
        struct.unpack('<4sIIIIIII', header)

    if magic != b'ZPKG':
        raise ValueError('not a supported Psychonauts .pkg file')

    if version != 1:
        raise ValueError('unsupported version: %u' % version)

    stream.seek(512, 0)
    records = [None] * records_count
    dir_map = [None] * records_count
    for i in range(records_count):
        record = stream.read(16)
        null1, type_offset, null2, name_offset, data_offset, data_size = \
            struct.unpack('<BHBIII', record)

        if null1 != 0 or null2 != 0:
            raise ValueError("expected null byte (null1: %u, null2: %u)" % (null1, null2))

        records[i] = (name_offset, type_offset, data_offset, data_size)

    stream.seek(dirs_offset, 0)
    dir_name_buffer = []
    SEP = os.path.sep.encode('utf-8')
    #	sys.stdout.write(" char     unknown1     unknown2    record id  start index    end index\n")
    for i in range(dirs_size):
        record = stream.read(12)
        ch, null, unknown1, unknown2, record_id, start_index, end_index = \
            struct.unpack('<cBHHHHH', record)

        if null != 0:
            raise ValueError("expected null byte but got %u" % null)

        #		sys.stdout.write(ch.decode('ascii'))
        #		sys.stdout.write("%5c  %11d  %11d  %11d  %11d  %11d\n" % (
        #			ch.decode('ascii'), unknown1, unknown2, record_id, start_index, end_index))

        is_sep = ch == b'/'
        if is_sep:
            dir_name_buffer.append(SEP)
        else:
            dir_name_buffer.append(ch)

        if start_index != 0 and end_index != 0:
            if is_sep:
                dir_name = b''.join(dir_name_buffer)
            else:
                #				sys.stdout.write('\n')
                dir_name = b''.join(dir_name_buffer)
                dir_name_buffer = []
            dir_name = dir_name.decode('utf-8')

            for j in range(start_index, end_index):
                if dir_map[j] is not None:
                    raise ValueError('directory name for file already defined')
                dir_map[j] = dir_name
            # else dir name continuation

    stream.seek(names_offset, 0)
    names = stream.read(types_offset - names_offset)
    types = stream.read(data_offset - types_offset)

    for i, (name_offset, type_offset, data_offset, data_size) in enumerate(records):
        name_end = names.find(b'\0', name_offset)
        if name_end == -1:
            raise ValueError("could not find terminating null byte when parsing file name")
        name = names[name_offset:name_end].decode('utf-8')

        type_end = types.find(b'\0', type_offset)
        if type_end == -1:
            raise ValueError("could not find terminating null byte when parsing file type")
        ftype = types[type_offset:type_end].decode('utf-8')

        name += '.' + ftype
        dir_name = dir_map[i]
        if dir_name is not None:
            name = os.path.join(dir_name, name)

        yield name, data_offset, data_size