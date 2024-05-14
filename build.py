#!/usr/bin/env python3
"""
build.py

Build HTML output
"""


import re
import os
import argparse
import datetime
import subprocess
import shutil
import lxml.html


def main():
    p = argparse.ArgumentParser(usage=__doc__.rstrip())
    p.add_argument('--html', action='store_true', help="Build HTML output")
    p.add_argument('--no-clean', action='store_true', help="Skip removing old output")
    args = p.parse_args()

    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    dst_path = os.path.join('docs', 'items')
    dst_path_ipynb = os.path.join('docs', 'static', 'items')

    if os.path.isdir(dst_path) and not args.no_clean:
        shutil.rmtree(dst_path)
    if not os.path.isdir(dst_path):
        os.makedirs(dst_path)
    if os.path.isdir(dst_path_ipynb):
        shutil.rmtree(dst_path_ipynb)

    shutil.copytree(os.path.join('ipython', 'attachments'),
                    os.path.join(dst_path, 'attachments'))

    shutil.copytree('ipython', dst_path_ipynb,
                    ignore=lambda src, names: [x for x in names if not x.endswith('.ipynb')])

    shutil.copytree(os.path.join('ipython', 'attachments'),
                    os.path.join(dst_path_ipynb, 'attachments'))

    tags = parse_wiki_legacy_tags()
    titles, tags_new = generate_files(dst_path=dst_path)

    tags.update(tags_new)
    write_index(dst_path, titles, tags)

    if args.html:
        subprocess.check_call(['sphinx-build', '-b', 'html', '.', '_build/html'],
                              cwd='docs')


def write_index(dst_path, titles, tags):
    """
    Write index files under `dst_path`

    """
    titles = dict(titles)

    index_rst = os.path.join(dst_path, 'index.txt')

    # Write doctree
    toctree_items = []
    index_text = []

    # Fill in missing tags
    for fn in titles.keys():
        if fn not in tags or not tags[fn]:
            tags[fn] = ['Other examples']

    # Count tags
    tag_counts = {}
    for fn, tagset in tags.items():
        for tag in tagset:
            if tag not in tag_counts:
                tag_counts[tag] = 1
            else:
                tag_counts[tag] += 1
    tag_counts['Outdated'] = 1e99

    # Generate tree
    def get_section_name(tag_id):
        return ("idx_" +
                re.sub('_+', '_', re.sub('[^a-z0-9_]', "_", "_" + tag_id.lower())).strip('_'))

    tag_sets = {}
    for fn, tagset in tags.items():
        tagset = list(set(tagset))
        tagset.sort(key=lambda tag: -tag_counts[tag])
        if 'Outdated' in tagset:
            tagset = ['Outdated']
        tag_id = " / ".join(tagset[:2])
        tag_sets.setdefault(tag_id, set()).add(fn)

        if len(tagset[:2]) > 1:
            # Add sub-tag to the tree
            sec_name = get_section_name(tag_id)
            titles[sec_name] = tagset[1]
            tag_sets.setdefault(tagset[0], set()).add(sec_name)

    tag_sets = list(tag_sets.items())
    def tag_set_sort(item):
        return (1 if 'Outdated' in item[0] else 0,
                item)
    tag_sets.sort(key=tag_set_sort)

    # Produce output
    for tag_id, fns in tag_sets:
        fns = list(fns)
        fns.sort(key=lambda fn: titles[fn])

        section_base_fn = get_section_name(tag_id)
        section_fn = os.path.join(dst_path, section_base_fn + '.rst')

        if ' / ' not in tag_id:
            toctree_items.append(section_base_fn)

        non_idx_items = [fn for fn in fns if not fn.startswith('idx_')]

        if non_idx_items:
            index_text.append("\n{0}\n{1}\n\n".format(tag_id, "-"*len(tag_id)))
            for fn in non_idx_items:
                index_text.append(":doc:`{0} <items/{1}>`\n".format(titles[fn], fn))

        with open(section_fn, 'w', encoding='utf-8') as f:
            sec_title = titles.get(section_base_fn, tag_id)
            f.write("{0}\n{1}\n\n".format(sec_title, "="*len(sec_title)))

            sub_idx = [fn for fn in fns if fn.startswith('idx')]

            if sub_idx:
                f.write(".. toctree::\n"
                        "   :maxdepth: 1\n\n")
                for fn in sub_idx:
                    f.write("   {0}\n".format(fn))
                f.write("\n\n")

            f.write(".. toctree::\n"
                    "   :maxdepth: 1\n\n")
            for fn in fns:
                if fn in sub_idx:
                    continue
                f.write("   {0}\n".format(fn))

    # Write index
    with open(index_rst, 'w', encoding='utf-8') as f:
        f.write(".. toctree::\n"
                "   :maxdepth: 1\n"
                "   :hidden:\n\n")
        for fn in toctree_items:
            f.write("   items/%s\n" % (fn,))
        f.write("\n\n")
        f.write('.. raw:: html\n\n   <div id="cookbook-index">\n\n')
        f.write("".join(index_text))
        f.write('\n\n.. raw:: html\n\n   </div>\n')
        f.close()


def generate_files(dst_path):
    """
    Read all .ipynb files and produce .rst under `dst_path`

    Returns
    -------
    titles : dict
        Dictionary {file_basename: notebook_title, ...}
    tags : dict
        Dictionary {file_basename: set([tag1, tag2, ...]), ...}
    """
    titles = {}
    tags = {}

    legacy_editors = parse_wiki_legacy_users()
    created, modified = parse_wiki_legacy_timestamps()

    for fn in sorted(os.listdir('ipython')):
        if not fn.endswith('.ipynb'):
            continue
        fn = os.path.join('ipython', fn)
        basename = os.path.splitext(os.path.basename(fn))[0]

        # Get old wiki editors
        editors = list(legacy_editors.get(basename, []))

        # Get names from Git
        created_stamp = created.get(basename, 0)
        modified_stamp = modified.get(basename, created_stamp)
        p = subprocess.Popen(['git', 'log', '--format=%at:%an', 'ef45029096..', fn],
                             stdout=subprocess.PIPE, encoding='utf-8')
        names, _ = p.communicate()
        for name in names.splitlines():
            timestamp, name = name.strip().split(':', 1)
            timestamp = int(timestamp)
            if name and name not in editors:
                editors.append(name)
            if created_stamp is None:
                created_stamp = timestamp
            if timestamp > modified_stamp:
                modified_stamp = timestamp

        # Continue
        title, tagset = convert_file(dst_path, fn, editors,
                                     created_stamp,
                                     modified_stamp)
        titles[basename] = title
        if tagset:
            tags[basename] = tagset

    return titles, tags


def convert_file(dst_path, fn, editors, created, modified):
    """
    Convert .ipynb to .rst, placing output under `dst_path`

    Returns
    -------
    title : str
        Title of the notebook
    tags : set of str
        Tags given in the notebook file

    """
    print(fn)
    subprocess.check_call(['jupyter', 'nbconvert', '--to', 'html',
                           '--output-dir', os.path.abspath(dst_path),
                           os.path.abspath(fn)],
                          cwd=dst_path, stderr=subprocess.STDOUT)

    basename = os.path.splitext(os.path.basename(fn))[0]
    rst_fn = os.path.join(dst_path, basename + '.rst')
    html_fn = os.path.join(dst_path, basename + '.html')

    title = None
    tags = set()
    editors = list(editors)
    legacy_editors = True

    lines = []

    # Parse and munge HTML
    tree = lxml.html.parse(html_fn)
    os.unlink(html_fn)

    root = tree.getroot()
    head = root.find('head')
    try:
        container, = root.xpath("//div[@id='notebook-container']")
    except ValueError:
        container, = root.xpath("//body[@class='jp-Notebook']")

    headers = container.xpath('//h1')
    if headers:
        title = headers[0].text
        h1_parent = headers[0].getparent()
        h1_parent.remove(headers[0])

    lines.extend([".. raw:: html", ""])

    for element in head.getchildren():
        if element.tag in ('script',):
            text = lxml.html.tostring(element, encoding='utf-8').decode('utf-8')
            lines.extend("   " + x for x in text.splitlines())

    text = lxml.html.tostring(container, encoding='utf-8').decode('utf-8')

    m = re.search(r'<p>TAGS:\s*(.*)\s*</p>', text)
    if m:
        tag_line = m.group(1).strip().replace(';', ',')
        tags.update([x.strip() for x in tag_line.split(",")])
        text = text[:m.start()] + text[m.end():]

    m = re.search(r'<p>AUTHORS:\s*(.*)\s*</p>', text)
    if m:
        # Author lines override editors
        if legacy_editors:
            editors = []
            legacy_editors = False
        author_line = m.group(1).strip().replace(';', ',')
        for author in author_line.split(","):
            author = author.strip()
            if author and author not in editors:
                editors.append(author)

        text = text[:m.start()] + text[m.end():]

    text = text.replace('attachments/{0}/'.format(basename),
                        '../_static/items/attachments/{0}/'.format(basename))

    lines.extend("   " + x for x in text.splitlines())
    lines.append("")

    # Produce output
    text = "\n".join(lines)

    if not title:
        title = basename

    updateinfo = ""

    def fmt_time(timestamp):
        return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

    if created != 0 and modified != 0:
        updateinfo = ":Date: {0} (last modified), {1} (created)".format(fmt_time(modified),
                                                       fmt_time(created))
    elif created != 0:
        updateinfo = ":Date: {0} (created)".format(fmt_time(created))
    elif modified != 0:
        updateinfo = ":Date: {0} (last modified)".format(fmt_time(modified))

    authors = ", ".join(editors)
    text = "{0}\n{1}\n\n{2}\n\n{3}".format(title, "="*len(title),
                                           updateinfo,
                                           text)

    with open(rst_fn, 'w', encoding='utf-8') as f:
        f.write(text)
        if authors:
            f.write("\n\n.. sectionauthor:: {0}".format(authors))
    del text

    attach_dir = os.path.join('ipython', 'attachments', basename)
    if os.path.isdir(attach_dir) and len(os.listdir(attach_dir)) > 0:
        with open(rst_fn, 'a', encoding='utf-8') as f:
            f.write("""

.. rubric:: Attachments

""")
            for fn in sorted(os.listdir(attach_dir)):
                if os.path.isfile(os.path.join(attach_dir, fn)):
                    f.write('- :download:`%s <attachments/%s/%s>`\n' % (
                        fn, basename, fn))

    return title, tags


def parse_wiki_legacy_tags():
    tags = [None, None, None]
    items = {}

    with open('wiki-legacy-tags.txt', 'r', encoding='utf-8') as f:
        prev_line = None

        for line in f:
            if re.match(r'^====+\s*$', line):
                tags[0] = prev_line.strip()
                tags[1] = None
                tags[2] = None
                continue

            if re.match(r'^----+\s*$', line):
                tags[1] = prev_line.strip()
                tags[2] = None
                continue

            if re.match(r'^""""+\s*$', line):
                tags[2] = prev_line.strip()
                continue

            prev_line = line

            m = re.search(r'\[\[(.*?)(?:\|.*)?\]\]', line)
            if m:
                name = m.group(1).strip()
                name = re.sub('Cookbook/', '', name)
                name = re.sub('^/', '', name)
                name = name.replace('/', '_').replace(' ', '_')

                fn = os.path.join('ipython', name + '.ipynb')
                if os.path.isfile(fn):
                    basename = os.path.splitext(os.path.basename(fn))[0]
                    items.setdefault(basename, set()).update([x for x in tags if x])
                continue

    return items


def parse_wiki_legacy_users():
    items = {}

    with open('wiki-legacy-users.txt', 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            page, rest = line.split(':', 1)
            editors = [x.strip() for x in rest.split(',')]

            items[page] = editors

    return items


def parse_wiki_legacy_timestamps():
    created = {}
    modified = {}

    with open('wiki-legacy-timestamps.txt', 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            page, c, m = line.split()
            created[page] = int(c)
            modified[page] = int(m)

    return created, modified


if __name__ == "__main__":
    main()
