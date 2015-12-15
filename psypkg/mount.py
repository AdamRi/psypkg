from __future__ import division
import os
import sys

try:
    import llfuse
except ImportError:
    def mount(*args, **kwargs):
        raise ValueError('The llfuse python module is needed for this feature and could not be found')
else:
    from collections import OrderedDict
    import errno
    import weakref
    import stat
    import mmap


    class Entry(object):
        __slots__ = 'inode', '_parent', 'stat', '__weakref__'

        def __init__(self, inode, parent=None):
            self.inode = inode
            self.parent = parent
            self.stat = None

        @property
        def parent(self):
            return self._parent() if self._parent is not None else None

        @parent.setter
        def parent(self, parent):
            self._parent = weakref.ref(parent) if parent is not None else None


    class Dir(Entry):
        __slots__ = 'children',

        def __init__(self, inode, children=None, parent=None):
            Entry.__init__(self, inode, parent)
            if children is None:
                self.children = OrderedDict()
            else:
                self.children = children
                for child in children.values():
                    child.parent = self

        def __repr__(self):
            return 'Dir(%r, %r)' % (self.inode, self.children)


    class File(Entry):
        __slots__ = 'offset', 'size'

        def __init__(self, inode, offset, size, parent=None):
            Entry.__init__(self, inode, parent)
            self.offset = offset
            self.size = size

        def __repr__(self):
            return 'File(%r, %r, %r)' % (self.inode, self.offset, self.size)


    DIR_SELF = '.'.encode(sys.getfilesystemencoding())
    DIR_PARENT = '..'.encode(sys.getfilesystemencoding())


    class Operations(llfuse.Operations):
        __slots__ = 'archive', 'root', 'inodes', 'arch_st', 'data'

        def __init__(self, archive):
            llfuse.Operations.__init__(self)
            self.archive = archive
            self.arch_st = os.fstat(archive.fileno())
            self.root = Dir(llfuse.ROOT_INODE)
            self.inodes = {self.root.inode: self.root}
            self.root.parent = self.root

            encoding = sys.getfilesystemencoding()
            inode = self.root.inode + 1
            for filename, offset, size in read_index(archive):
                path = filename.split(os.path.sep)
                path, name = path[:-1], path[-1]
                enc_name = name.encode(encoding)
                name, ext = os.path.splitext(name)

                parent = self.root
                for i, comp in enumerate(path):
                    comp = comp.encode(encoding)
                    try:
                        entry = parent.children[comp]
                    except KeyError:
                        entry = parent.children[comp] = self.inodes[inode] = Dir(inode, parent=parent)
                        inode += 1

                    if type(entry) is not Dir:
                        raise ValueError(
                            "name conflict in archive: %r is not a directory" % os.path.join(*path[:i + 1]))

                    parent = entry

                i = 0
                while enc_name in parent.children:
                    sys.stderr.write("Warning: doubled name in archive: %s\n" % filename)
                    i += 1
                    enc_name = ("%s~%d%s" % (name, i, ext)).encode(encoding)

                parent.children[enc_name] = self.inodes[inode] = File(inode, offset, size, parent)
                inode += 1

            archive.seek(0, 0)
            self.data = mmap.mmap(archive.fileno(), 0, access=mmap.ACCESS_READ)

            # cache entry attributes
            for inode in self.inodes:
                entry = self.inodes[inode]
                entry.stat = self._getattr(entry)

        def destroy(self):
            self.data.close()
            self.archive.close()

        def lookup(self, parent_inode, name):
            try:
                if name == DIR_SELF:
                    entry = self.inodes[parent_inode]

                elif name == DIR_PARENT:
                    entry = self.inodes[parent_inode].parent

                else:
                    entry = self.inodes[parent_inode].children[name]

            except KeyError:
                raise llfuse.FUSEError(errno.ENOENT)
            else:
                return entry.stat

        def _getattr(self, entry):
            attrs = llfuse.EntryAttributes()

            attrs.st_ino = entry.inode
            attrs.st_rdev = 0
            attrs.generation = 0
            attrs.entry_timeout = 300
            attrs.attr_timeout = 300

            if type(entry) is Dir:
                nlink = 2 if entry is not self.root else 1
                size = 5

                for name, child in entry.children.items():
                    size += len(name) + 1
                    if type(child) is Dir:
                        nlink += 1

                attrs.st_mode = stat.S_IFDIR | 0o555
                attrs.st_nlink = nlink
                attrs.st_size = size
            else:
                attrs.st_nlink = 1
                attrs.st_mode = stat.S_IFREG | 0o444
                attrs.st_size = entry.size

            arch_st = self.arch_st
            attrs.st_uid = arch_st.st_uid
            attrs.st_gid = arch_st.st_gid
            attrs.st_blksize = arch_st.st_blksize
            attrs.st_blocks = 1 + ((attrs.st_size - 1) // attrs.st_blksize) if attrs.st_size != 0 else 0
            attrs.st_atime = arch_st.st_atime
            attrs.st_mtime = arch_st.st_mtime
            attrs.st_ctime = arch_st.st_ctime

            return attrs

        def getattr(self, inode):
            try:
                entry = self.inodes[inode]
            except KeyError:
                raise llfuse.FUSEError(errno.ENOENT)
            else:
                return entry.stat

        def access(self, inode, mode, ctx):
            try:
                entry = self.inodes[inode]
            except KeyError:
                raise llfuse.FUSEError(errno.ENOENT)
            else:
                st_mode = 0o555 if type(entry) is Dir else 0o444
                return (st_mode & mode) == mode

        def opendir(self, inode):
            try:
                entry = self.inodes[inode]
            except KeyError:
                raise llfuse.FUSEError(errno.ENOENT)
            else:
                if type(entry) is not Dir:
                    raise llfuse.FUSEError(errno.ENOTDIR)

                return inode

        def readdir(self, inode, offset):
            try:
                entry = self.inodes[inode]
            except KeyError:
                raise llfuse.FUSEError(errno.ENOENT)
            else:
                if type(entry) is not Dir:
                    raise llfuse.FUSEError(errno.ENOTDIR)

                names = list(entry.children)[offset:] if offset > 0 else entry.children
                for name in names:
                    child = entry.children[name]
                    yield name, child.stat, child.inode

        def releasedir(self, fh):
            pass

        def statfs(self):
            attrs = llfuse.StatvfsData()

            arch_st = self.arch_st
            attrs.f_bsize = arch_st.st_blksize
            attrs.f_frsize = arch_st.st_blksize
            attrs.f_blocks = arch_st.st_blocks
            attrs.f_bfree = 0
            attrs.f_bavail = 0

            attrs.f_files = len(self.inodes)
            attrs.f_ffree = 0
            attrs.f_favail = 0

            return attrs

        def open(self, inode, flags):
            try:
                entry = self.inodes[inode]
            except KeyError:
                raise llfuse.FUSEError(errno.ENOENT)
            else:
                if type(entry) is Dir:
                    raise llfuse.FUSEError(errno.EISDIR)

                if flags & 3 != os.O_RDONLY:
                    raise llfuse.FUSEError(errno.EACCES)

                return inode

        def read(self, fh, offset, length):
            try:
                entry = self.inodes[fh]
            except KeyError:
                raise llfuse.FUSEError(errno.ENOENT)

            if offset > entry.size:
                return bytes()

            i = entry.offset + offset
            j = i + min(entry.size - offset, length)
            return self.data[i:j]

        def release(self, fh):
            pass


    # based on http://code.activestate.com/recipes/66012/
    def deamonize(stdout='/dev/null', stderr=None, stdin='/dev/null'):
        # Do first fork.
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)  # Exit first parent.
        except OSError as e:
            sys.stderr.write("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror))
            sys.exit(1)

        # Decouple from parent environment.
        os.chdir("/")
        os.umask(0)
        os.setsid()

        # Do second fork.
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)  # Exit second parent.
        except OSError as e:
            sys.stderr.write("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror))
            sys.exit(1)

        # Open file descriptors
        if not stderr:
            stderr = stdout

        si = open(stdin, 'r')
        so = open(stdout, 'a+')
        se = open(stderr, 'a+')

        # Redirect standard file descriptors.
        sys.stdout.flush()
        sys.stderr.flush()

        os.close(sys.stdin.fileno())
        os.close(sys.stdout.fileno())
        os.close(sys.stderr.fileno())

        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())


    def mount(archive, mountpt, foreground=False, debug=False):
        archive = os.path.abspath(archive)
        mountpt = os.path.abspath(mountpt)
        with open(archive, "rb") as fp:
            ops = Operations(fp)
            args = ['fsname=psypkg', 'subtype=psypkg', 'ro']

            if debug:
                foreground = True
                args.append('debug')

            if not foreground:
                deamonize()

            llfuse.init(ops, mountpt, args)
            try:
                llfuse.main(single=False)
            finally:
                llfuse.close()

