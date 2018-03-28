import re
import pathlib
import datetime as dt
import urllib.parse

import frontmatter
from typing import (List, Dict, Optional, Union, Any, Callable)
from dateutil import parser as duparser
from slugify import slugify

from ibooks_highlights.util import (
    cmp_to_key, query_compare_no_asset_id, TEMPLATE_ENVIRONMENT,
    NS_TIME_INTERVAL_SINCE_1970)
from ibooks_highlights.ibooksdb import SqliteQueryType


class BookMetadataError(Exception):
    pass


class Annotation(object):

    def __init__(self, location: str, selected_text: str=None, 
                 note: str=None, represent_text: str=None, chapter: str=None, 
                 style: str=None, modified_date: dt.datetime=None) -> None:

        if (selected_text is None) and (note is None):
            raise ValueError('specify either selected_text or note')

        self.location = location
        self.selected_text = selected_text

        if represent_text is not None:
            represent_text = represent_text.strip()
        self.represent_text = represent_text

        self.chapter = chapter
        self.style = style
        self.note = note
        self.modified_date = modified_date

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class Book(object):

    def __init__(self, asset_id: str=None, 
                 filename: pathlib.Path=None) -> None:

        args_present = asset_id is not None
        file_present = filename is not None

        if args_present == file_present:
            raise ValueError('specify either asset_id or filename')

        self._modified_date: Optional[dt.datetime] = None
        self._annotations: List[Annotation] = []
        self._sync_notes = True

        if args_present:
            self._asset_id = asset_id
            self._author: Optional[str] = None
            self._title: Optional[str] = None
            self._prev_content: Optional[str] = None
            self._reader_notes = ''

        if file_present:
            self._process_file(filename)

    def _process_file(self, filename: pathlib.Path) -> None:

        self._filename = filename.name

        book = frontmatter.load(filename)

        if 'asset_id' not in book.keys():
            raise BookMetadataError('asset_id missing')

        self._asset_id = book['asset_id']
        self._author = book['author']
        self._title = book['title']

        if 'modified_date' in book.keys():
            self._modified_date = duparser.parse(book['modified_date'])

        if 'sync_notes' in book.keys():
            self._sync_notes = bool(book['sync_notes'])

        self._prev_content = book.content

        self._reader_notes = ''

        reader_notes_start = None
        ibooks_notes_start = None

        prev_content_lines = self._prev_content.splitlines()

        for i, line in enumerate(prev_content_lines):
            if """<a name="my_notes_dont_delete"></a>""" in line:
                reader_notes_start = i
            if """<a name="ibooks_notes_dont_delete"></a>""" in line:
                ibooks_notes_start = i

        # if not present, abort
        if reader_notes_start is None and ibooks_notes_start is None:
            return

        # if same line, that's not good
        if reader_notes_start == ibooks_notes_start:
            raise BookMetadataError('Note section identifiers on same line')

        # if different line, select the appropriate portion of the content
        if reader_notes_start is None:
            reader_lines = prev_content_lines[3:ibooks_notes_start]
        elif reader_notes_start < ibooks_notes_start:
            reader_lines = prev_content_lines[
                reader_notes_start+1:ibooks_notes_start]
        else:
            reader_lines = prev_content_lines[reader_notes_start+1:]

        self._reader_notes = '\n'.join(reader_lines).strip()

    def __str__(self) -> str:
        asset_id = self._asset_id[:8].ljust(8)
        mod = ' '
        if self.is_modified:
            mod = '*'
        return f'{asset_id} {mod} {self.num_annotations}\t{self._title}'

    # I need umläuts :-)
    def _yaml_str(cls, txt: str) -> str:
        exp = '[^A-Za-z0-9 ]+'
        return re.sub(exp, '', txt)

    @property
    def author(self) -> str:
        return self._author

    @author.setter
    def author(self, value: str) -> None:
        if value is None:
            value = 'Unknown'
        #self._author = self._yaml_str(value)
        self._author = value

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:

        if value is None:
            value = 'Unknown'
        #self._title = self._yaml_str(value)
        self._title = value

        slug = slugify(value)
        asset_id = self._asset_id[:8].lower()
        self._filename = f'{slug}-{asset_id}.md'

    @property
    def asset_id(self) -> str:
        return self._asset_id

    @property
    def is_modified(self) -> bool:
        if self._modified_date is None:
            if self.num_annotations > 0:
                return True
            else:
                return False

        if len(self._annotations) is 0:
            return False

        anno_max = max([
            anno.modified_date
            for anno in self._annotations
        ])
        return anno_max > self._modified_date

    @property
    def annotations(self) -> List[Annotation]:
        return self._annotations

    @annotations.setter
    def annotations(self, anno: List[Annotation]) -> None:
        self._annotations = anno
        self._annotations.sort(key=cmp_to_key(query_compare_no_asset_id))

    @property
    def num_annotations(self) -> int:
        return len(self._annotations)

    @property
    def prev_content(self) -> str:
        return self._prev_content

    @property
    def content(self) -> str:
        template = TEMPLATE_ENVIRONMENT.get_template("markdown_template.md")

        # print(self._reader_notes[:1000])

        md = template.render(
            title=self._title,
            author=self._author,
            title_encoded=urllib.parse.quote(self._title),
            author_encoded=urllib.parse.quote(self._author),
            highlights=self.annotations,
            reader_notes=self._reader_notes
        )
        return md

    def write(self, path: pathlib.Path) -> None:

        if not path.is_dir():
            raise NotADirectoryError(f'{str(path)} is not a directory')

        if not self._sync_notes:
            print('sync locked for', self._title)
            return
        
        print('updating', self._title)

        mod_date = max([
            anno.modified_date
            for anno in self._annotations
        ])
        mod_date_str = mod_date.isoformat()

        fmpost = frontmatter.Post(
            self.content,
            asset_id=self._asset_id,
            title=self.title,
            author=self.author,
            modified_date=mod_date_str
        )

        fn = path / self._filename

        with open(fn, 'w') as f:
            s = frontmatter.dumps(fmpost)
            f.write(s)


class BookList(object):

    def __init__(self, path: pathlib.Path) -> None:

        if not path.is_dir():
            raise NotADirectoryError(f'{str(path)} is not a directory')

        self._path = path
        self.books: dict = {}

        if self._path.exists():
            self.books = self._load_books(self._path)

    def _load_books(self, path: pathlib.Path) -> Dict[str, Book]:

        book_files = path.glob('*.md')

        md_books = {}
        for bf in book_files:
            try:
                book = Book(filename=bf)
                md_books[book.asset_id] = book
            except BookMetadataError:
                pass

        return md_books

    def _get_create_book(self, asset_id: str) -> Book:

        if asset_id not in self.books:
            book = Book(asset_id=asset_id)
            self.books[asset_id] = book

        return self.books[asset_id]

    def populate_annotations(self, annos: SqliteQueryType) -> None:

        res = [
            r
            for r in annos
            if r['asset_id'] is not None and
            ((r['selected_text'] is not None) or (r['note'] is not None))
        ]

        for r in res:
            book = self._get_create_book(str(r['asset_id']))
            if book.title is None:
                book.title = str(r['title'])
            if book.author is None:
                book.author = str(r['author'])

        anno_group: Dict[str, List[Annotation]] = {}
        for r in res:
            asset_id = str(r['asset_id'])
            if asset_id not in anno_group:
                anno_group[asset_id] = []

            location = str(r['location']) if r['location'] else None
            selected_text = (
                str(r['selected_text']) if r['selected_text'] else None)
            note = str(r['note']) if r['note'] else None
            represent_text = (
                str(r['represent_text']) if r['represent_text'] else None)
            chapter = str(r['chapter']) if r['chapter'] else None
            style = str(r['style']) if r['style'] else None

            anno = Annotation(
                location=location,
                selected_text=selected_text,
                note=note,
                represent_text=represent_text,
                chapter=chapter,
                style=style,
                modified_date=dt.datetime.fromtimestamp(
                    NS_TIME_INTERVAL_SINCE_1970 + int(r['modified_date'])),
            )
            anno_group[asset_id].append(anno)

        for asset_id, anno_itr in anno_group.items():
            self.books[asset_id].annotations = anno_itr

    def write_modified(self, path: pathlib.Path=None, 
                       force: bool=False) -> None:

        if path is None:
            path = self._path

        if not path.is_dir():
            raise NotADirectoryError(f'{str(path)} is not a directory')

        path.mkdir(parents=True, exist_ok=True)

        for book in self.books.values():
            if (not book.is_modified) and (not force):
                continue
            book.write(path)
