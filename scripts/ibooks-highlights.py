#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse

from ibooks_highlights.models import BookList
from ibooks_highlights import ibooksdb



def print_book_list(book_list):

    books = book_list.books.values()
    books = sorted(books, key=lambda b: b.title)

    for book in books:
        print(book)


def write_book_notes(path):
    book_list.write_modified(path)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='iBooks highlights exporter')
    parser.add_argument(
        '-o', action="store", default="books", dest="dname",
        help="Specify output directory (default: books)")
    parser.add_argument(
        '--list', action="store_true", 
        help="Lists a books having highlights.")

    args = parser.parse_args()

    book_list = BookList(args.dname)
    annos = ibooksdb.fetch_annotations()
    book_list.populate_annotations(annos)

    if args.list:
        print_book_list(book_list)
    else:
        write_book_notes(args.dname)