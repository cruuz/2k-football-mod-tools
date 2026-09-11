"""Named CPU books in a built (including expanded) archive.

This isolated Fine-tune session deliberately has no numeric-index project from
before cloning. Its recipes bind each selector to a book name and source hash.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import zlib

from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core.apf2k8_book_clone import compare_untouched_packs, compare_executable
from mod_editor.core.errors import ValidationError
import apf_outer
import playbook_inventory


def book_catalog(index):
    archive = apf_outer.parse_archive(index)
    labels = identity.parse_roster_identity(identity.read_disc_roster(index)).labels
    names = set(splb.STOCK_BOOKS.values()) | {label.kind for label in labels}
    by_id = {entry.name_id: entry for entry in archive.entries}
    books = {}
    for name in sorted(names):
        entry = by_id.get(identity.filename_id(name))
        if entry is not None:
            book = splb.read_book(index, entry.table_index)
            if book.name != name:
                raise ValidationError('Book label type and resource name disagree')
            books[entry.table_index] = book
    return books


def master_inventory(index):
    source = identity.read_resource(index, zlib.crc32(b'PLAYBOOK_MASTER.IFF'), 'mpb', 'PLAY')
    return playbook_inventory.parse_apf_body(source[3], source[1].table_index, 0), source[3]


class BookContentSession:
    def __init__(self, index):
        self.source = SimpleNamespace(index_0a=Path(index).resolve())
        self.books = book_catalog(self.source.index_0a)
        self.book_choices = {i: book.name for i, book in self.books.items()}
        self.inventory, self.master = master_inventory(self.source.index_0a)
        self.source_ready = True
        self.changes = ()
        self.last_ladder_messages = []

    def master_inventory(self):
        return self.inventory

    def master_categories(self):
        return tuple({'index': i, 'name': splb.PERSONNEL_NAMES[i],
                      'row': self.master[0x44+i*16+4] & 63,
                      'roles': tuple(self.master[0x44+i*16+5:0x44+i*16+16])}
                     for i in range(splb.CATEGORY_COUNT))

    def retail_formation_packages(self):
        # Defaults remain the pinned retail pairings, not a census of edited clones.
        return {i: tuple((c, len(cats)-n) for n, c in enumerate(cats))
                for i, cats in enumerate(splb.FORMATION_PERSONNEL_CATEGORIES)}

    def staged_splb_changes(self):
        return self.changes

    def staged_splb_outers(self):
        return tuple(sorted({c.outer_index for c in self.changes}))

    def stage_splb_membership(self, changes, *, replace_outer=None):
        changes = tuple(changes)
        updated = tuple(c for c in self.changes if c.outer_index != replace_outer) + changes
        messages = []
        for outer in {c.outer_index for c in updated}:
            if outer not in self.books:
                raise ValidationError('The selected book is not in this game folder')
            compiled = splb.compile_book(self.books[outer], [c for c in updated if c.outer_index == outer])
            splb.verify_book(self.books[outer].body, compiled.replacement,
                             [c for c in updated if c.outer_index == outer])
            messages.extend(compiled.report['personnel_ladder']['messages'])
        self.changes = updated
        self.last_ladder_messages = messages
        return len(changes)

    def save_recipe(self, path):
        value = {'schema': 'apf_named_book_edits/v1', 'master_sha256': hashlib.sha256(self.master).hexdigest(), 'books': [
            {'name': self.books[i].name, 'sha256': hashlib.sha256(self.books[i].body).hexdigest(),
             'changes': [splb.change_metadata(c) for c in self.changes if c.outer_index == i]}
            for i in self.staged_splb_outers()]}
        Path(path).write_bytes((json.dumps(value, indent=2, sort_keys=True)+'\n').encode())

    def load_recipe(self, path):
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        if value.get('schema') != 'apf_named_book_edits/v1':
            raise ValidationError('Choose a named book edits recipe')
        if value.get('master_sha256') != hashlib.sha256(self.master).hexdigest():
            raise ValidationError('Recipe MASTER contents differ from this game folder')
        by_name = {book.name: book for book in self.books.values()}
        changes = []
        seen = set()
        for row in value['books']:
            book = by_name.get(row['name'])
            if (book is None or book.name in seen or
                    hashlib.sha256(book.body).hexdigest() != row['sha256']):
                raise ValidationError('Recipe book contents differ from this game; use its original source folder')
            seen.add(book.name)
            for change in row['changes']:
                changes.append(splb.change_from_mapping(dict(change, outer_index=book.outer_index)))
        previous = self.changes
        self.changes = ()
        try:
            self.stage_splb_membership(changes)
        except Exception:
            self.changes = previous
            raise

    def build_to(self, destination, progress=lambda *_args: None):
        if master_inventory(self.source.index_0a)[1] != self.master:
            raise ValidationError("MASTER changed after editing; reopen this folder and review it")
        for outer in self.staged_splb_outers():
            if splb.read_book(self.source.index_0a, outer).body != self.books[outer].body:
                raise ValidationError('Source book changed after editing; reopen this folder and review it')
        return build_content_folder(self.source.index_0a, self.changes, destination, progress)


def build_content_folder(index, changes, destination, progress=lambda *_args: None):
    index = Path(index).resolve()
    if Path(destination).is_symlink():
        raise ValidationError('Output directory must not be a symlink')
    destination = Path(destination).resolve()
    if destination == index.parent or destination in index.parent.parents or index.parent in destination.parents:
        raise ValidationError('Choose a separate new output folder outside the source game')
    changes = tuple(changes)
    if not changes:
        raise ValidationError('Edit at least one book before building')
    compiled = [splb.build_book_patch(index, [c for c in changes if c.outer_index == outer])
                for outer in sorted({c.outer_index for c in changes})]
    archive = apf_outer.parse_archive(index)
    destination.mkdir(parents=False, exist_ok=False)
    try:
        for pack in archive.packs:
            progress(f'Copying {pack.name}', 0, 1)
            shutil.copyfile(pack.path, destination / pack.name)
        if (index.parent / 'default.xex').is_file():
            shutil.copyfile(index.parent / 'default.xex', destination / 'default.xex')
        allowed = []
        for result in compiled:
            entry = archive.entries[result.outer_index]
            cursor = 0
            for segment in entry.segments:
                with (destination / segment.pack_name).open('r+b') as stream:
                    stream.seek(segment.pack_offset)
                    stream.write(result.entry_bytes[cursor:cursor+segment.size])
                cursor += segment.size
            allowed.append((entry.virtual_offset, entry.virtual_end))
        output = destination / index.name
        final_archive = apf_outer.parse_archive(output)
        if [(e.name_id, e.virtual_offset, e.size) for e in archive.entries] != [
                (e.name_id, e.virtual_offset, e.size) for e in final_archive.entries]:
            raise ValidationError('Book content edit changed the archive directory')
        for result in compiled:
            final = splb.read_book(output, result.outer_index)
            source = splb.read_book(index, result.outer_index)
            if final.body != result.replacement:
                raise ValidationError('Published book differs from the compiled selection')
            splb.verify_book(source.body, final.body, [c for c in changes if c.outer_index == result.outer_index])
        receipt = {'schema': 'apf_named_book_build/v1', 'books': [c.report for c in compiled],
                   'untouched_pack_bytes_compared': compare_untouched_packs(archive, final_archive, allowed),
                   'book_identity': identity.disc_book_identity_report(output),
                   'executable': compare_executable(index.parent, destination),
                   'runtime_status': 'UNWITNESSED'}
        (destination / 'book-content-receipt.json').write_bytes(
            (json.dumps(receipt, indent=2, sort_keys=True)+'\n').encode())
        return receipt
    except BaseException:
        shutil.rmtree(destination)
        raise
