import os
import sys

from psypkg.mount import mount
from psypkg.list import print_list
from psypkg.unpack import unpack_files, unpack

import argparse


# from https://gist.github.com/sampsyo/471779
class AliasedSubParsersAction(argparse._SubParsersAction):
    class _AliasedPseudoAction(argparse.Action):
        def __init__(self, name, aliases, help):
            dest = name
            if aliases:
                dest += ' (%s)' % ','.join(aliases)
            sup = super(AliasedSubParsersAction._AliasedPseudoAction, self)
            sup.__init__(option_strings=[], dest=dest, help=help)

    def add_parser(self, name, **kwargs):
        if 'aliases' in kwargs:
            aliases = kwargs['aliases']
            del kwargs['aliases']
        else:
            aliases = []

        parser = super(AliasedSubParsersAction, self).add_parser(name, **kwargs)

        # Make the aliases work.
        for alias in aliases:
            self._name_parser_map[alias] = parser
        # Make the help text reflect them, first removing old help entry.
        if 'help' in kwargs:
            help = kwargs.pop('help')
            self._choices_actions.pop()
            pseudo_action = self._AliasedPseudoAction(name, aliases, help)
            self._choices_actions.append(pseudo_action)

        return parser


def add_common_args(parser):
    parser.add_argument('archive', help='Psychonauts .pkg archive')
    parser.add_argument('-0', '--print0', action='store_true', default=False,
                        help='seperate file names with nil bytes')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        help='print verbose output')


SORT_ALIASES = {
    "s": "size",
    "S": "-size",
    "o": "offset",
    "O": "-offset",
    "n": "name",
    "N": "-name"
}

# for Python 3
if not hasattr(__builtins__, 'cmp'):
    def cmp(a, b):
        return (a > b) - (a < b)

CMP_FUNCS = {
    "size": lambda lhs, rhs: cmp(lhs[2], rhs[2]),
    "-size": lambda lhs, rhs: cmp(rhs[2], lhs[2]),

    "offset": lambda lhs, rhs: cmp(lhs[1], rhs[1]),
    "-offset": lambda lhs, rhs: cmp(rhs[1], lhs[1]),

    "name": lambda lhs, rhs: cmp(lhs[0], rhs[0]),
    "-name": lambda lhs, rhs: cmp(rhs[0], lhs[0])
}


def sort_func(sort):
    cmp_funcs = []
    for key in sort.split(","):
        key = SORT_ALIASES.get(key, key)
        try:
            func = CMP_FUNCS[key]
        except KeyError:
            raise ValueError("unknown sort key: " + key)
        cmp_funcs.append(func)

    def do_cmp(lhs, rhs):
        for cmp_func in cmp_funcs:
            i = cmp_func(lhs, rhs)
            if i != 0:
                return i
        return 0

    return do_cmp


def main(argv):
    parser = argparse.ArgumentParser(description='unpack, list and mount Psychonauts .pkg archives')
    parser.register('action', 'parsers', AliasedSubParsersAction)
    parser.set_defaults(print0=False, verbose=False)

    subparsers = parser.add_subparsers(metavar='command')

    unpack_parser = subparsers.add_parser('unpack', aliases=('x',), help='unpack archive')
    unpack_parser.set_defaults(command='unpack')
    unpack_parser.add_argument('-C', '--dir', type=str, default='.',
                               help='directory to write unpacked files')
    add_common_args(unpack_parser)
    unpack_parser.add_argument('files', metavar='file', nargs='*', help='files and directories to unpack')

    list_parser = subparsers.add_parser('list', aliases=('l',), help='list archive contens')
    list_parser.set_defaults(command='list')
    list_parser.add_argument('-u', '--human-readable', dest='human', action='store_true', default=False,
                             help='print human readable file sizes')
    list_parser.add_argument('-d', '--details', action='store_true', default=False,
                             help='print file offsets and sizes')
    list_parser.add_argument('-s', '--sort', dest='sort_func', metavar='KEYS', type=sort_func, default=None,
                             help='sort file list. Comma seperated list of sort keys. Keys are "size", "offset", and "name". '
                                  'Prepend "-" to a key name to sort in descending order.')
    add_common_args(list_parser)

    mount_parser = subparsers.add_parser('mount', aliases=('m',), help='fuse mount archive')
    mount_parser.set_defaults(command='mount')
    mount_parser.add_argument('-d', '--debug', action='store_true', default=False,
                              help='print debug output (implies -f)')
    mount_parser.add_argument('-f', '--foreground', action='store_true', default=False,
                              help='foreground operation')
    mount_parser.add_argument('archive', help='Psychonauts .pkg archive')
    mount_parser.add_argument('mountpt', help='mount point')

    args = parser.parse_args(argv)

    delim = '\0' if args.print0 else '\n'

    if args.verbose:
        callback = lambda name: sys.stdout.write("%s%s" % (name, delim))
    else:
        callback = lambda name: None

    if args.command == 'list':
        with open(args.archive, "rb") as stream:
            print_list(stream, args.details, args.human, delim, args.sort_func)

    elif args.command == 'unpack':
        with open(args.archive, "rb") as stream:
            if args.files:
                unpack_files(stream, set(name.strip(os.path.sep) for name in args.files), args.dir, callback)
            else:
                unpack(stream, args.dir, callback)

    elif args.command == 'mount':
        mount(args.archive, args.mountpt, args.foreground, args.debug)
    else:
        raise ValueError('unknown command: %s' % args.command)

main(sys.argv[1:])
