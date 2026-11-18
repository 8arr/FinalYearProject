"""Builds Word versions of the markdown reports.

    pip install pypandoc_binary python-docx
    python report/make_docx.py

Anything in [square brackets] is highlighted yellow so it is easy to find.
"""
import copy
import os
import re

import pypandoc
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["proposal", "interim_report", "project_plan"]
PLACEHOLDER = re.compile(r"(\[[^\]]*\])")


def add_borders(table):
    props = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), "999999")
        borders.append(el)
    props.append(borders)


def highlight_placeholders(paragraph):
    for run in list(paragraph.runs):
        parts = PLACEHOLDER.split(run.text)
        if len(parts) == 1:
            continue
        anchor = run._r
        for part in parts:
            if not part:
                continue
            clone = copy.deepcopy(run._r)
            anchor.addnext(clone)
            anchor = clone
            new_run = next(r for r in paragraph.runs if r._r is clone)
            new_run.text = part
            if PLACEHOLDER.fullmatch(part):
                new_run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        run._r.getparent().remove(run._r)


def tidy(path):
    doc = Document(path)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(2.2)
    for table in doc.tables:
        add_borders(table)
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(9.5)
    for shape in doc.inline_shapes:
        ratio = shape.height / shape.width
        shape.width = Cm(16.5)
        shape.height = int(shape.width * ratio)

    def paragraphs():
        yield from doc.paragraphs
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from cell.paragraphs

    for p in paragraphs():
        highlight_placeholders(p)
    doc.save(path)


def main():
    for name in FILES:
        src = os.path.join(HERE, f"{name}.md")
        out = os.path.join(HERE, f"{name}.docx")
        pypandoc.convert_file(src, "docx", outputfile=out, extra_args=[f"--resource-path={HERE}"])
        tidy(out)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
