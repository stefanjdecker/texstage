# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
"""The PowerPoint file: one picture slide per page with its notes, and on live slides a
content add-in object covering the whole slide (docs/design.md, sections 4 and 5).

python-pptx writes pictures and notes; the add-in object is raw OOXML, as verified in
spike S1 (docs/design.md, section 9.1):

    ppt/webextensions/webextensionN.xml   which add-in, its properties, a snapshot image
    p:graphicFrame (in mc:AlternateContent) on the slide, referring to that part; the
    mc:Fallback is the slide picture for programs without web add-ins

The add-in is referenced as a sideloaded development add-in (storeType Registry, store
developer). Its properties are JSON-encoded, as Office.js document settings are stored.

Every quiz server has its own add-in, with an ID derived from the server's address
(addin_id): PowerPoint loads an add-in's page from the address in its registration
(texstage addin install), so the add-in the live slides reference is what decides the
server of a PPTX - at build time (--server), or afterwards with retarget().
"""
from __future__ import annotations

import json
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import quoteattr

from lxml import etree
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.util import Emu

ADDIN_NAMESPACE = uuid.UUID("d83300a7-7a68-4a22-a48a-4cd437030a2e")    # texstage
ADDIN_VERSION = "1.0.0.0"

RT_WEBEXT = "http://schemas.microsoft.com/office/2011/relationships/webextension"
CT_WEBEXT = "application/vnd.ms-office.webextension+xml"
NS_WE = "http://schemas.microsoft.com/office/webextensions/webextension/2010/11"
SLIDE_HEIGHT = Emu(6858000)          # 7.5 in, PowerPoint's default height


def origin(server: str) -> str:
    """A server address as its origin: 'HTTPS://Quiz.example.org:443/x' -> 'https://quiz.example.org'."""
    u = urlsplit(server.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError(f"not a server address: {server!r} (e.g. http://localhost:8470)")
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
    port = f":{u.port}" if u.port and u.port != {"http": 80, "https": 443}[u.scheme] else ""
    return f"{u.scheme}://{host}{port}"


def addin_id(server: str) -> str:
    """The ID of this server's add-in (the same on every PC)."""
    return str(uuid.uuid5(ADDIN_NAMESPACE, origin(server)))


def webextension_xml(props: dict, snapshot_rid: str, addin: str) -> bytes:
    prop_xml = "".join(f"<we:property name={quoteattr(k)} value={quoteattr(json.dumps(v, ensure_ascii=False))}/>"
                       for k, v in props.items())
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<we:webextension xmlns:we="{NS_WE}" id="{{{str(uuid.uuid4()).upper()}}}">'
            f'<we:reference id="{addin}" version="{ADDIN_VERSION}" store="developer" storeType="Registry"/>'
            f'<we:alternateReferences/>'
            f'<we:properties>{prop_xml}</we:properties>'
            f'<we:bindings/>'
            f'<we:snapshot xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            f'r:embed="{snapshot_rid}"/>'
            f'</we:webextension>').encode("utf-8")


class PptxDeck:
    """Slides are added first (their IDs go into the bundle), add-ins afterwards (their
    properties name the bundle)."""

    def __init__(self, slide_size_pt: tuple[float, float], server: str):
        self.addin = addin_id(server)
        self.prs = Presentation()
        width_pt, height_pt = slide_size_pt
        self.prs.slide_height = SLIDE_HEIGHT
        self.prs.slide_width = Emu(round(SLIDE_HEIGHT * width_pt / height_pt))
        self.layout = self.prs.slide_layouts[6]          # blank
        self.images = []                                 # image part per slide
        self.webextensions = 0

    def add_slide(self, png: bytes, notes: str) -> int:
        """A picture slide; returns its slide ID (p:sldId/@id), which the add-ins compare
        with the slide shown in the slideshow."""
        slide = self.prs.slides.add_slide(self.layout)
        pic = slide.shapes.add_picture(BytesIO(png), 0, 0, self.prs.slide_width, self.prs.slide_height)
        pic.name = "slide"
        self.images.append(slide.part.related_part(pic._element.blip_rId))
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        return slide.slide_id

    def add_addin(self, index: int, props: dict, name: str):
        """The add-in object over the whole slide `index` (0-based); its snapshot (what
        PowerPoint shows until the add-in has loaded) is the slide picture."""
        slide = self.prs.slides[index]
        image = self.images[index]
        self.webextensions += 1
        pkg = self.prs.part.package
        part = Part(PackURI(f"/ppt/webextensions/webextension{self.webextensions}.xml"), CT_WEBEXT, pkg, b"")
        part._blob = webextension_xml(props, part.relate_to(image, RT.IMAGE), self.addin)
        we_rid = slide.part.relate_to(part, RT_WEBEXT)
        pic_rid = slide.part.relate_to(image, RT.IMAGE)
        tree = slide.shapes._spTree
        shape_id = max(int(x) for x in tree.xpath(".//p:cNvPr/@id")) + 1
        cx, cy = self.prs.slide_width, self.prs.slide_height
        name = quoteattr(name)
        tree.append(etree.fromstring(f"""
<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
    xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
    xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <mc:Choice xmlns:we="{NS_WE}" Requires="we">
    <p:graphicFrame>
      <p:nvGraphicFramePr>
        <p:cNvPr id="{shape_id}" name={name}/>
        <p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr>
        <p:nvPr/>
      </p:nvGraphicFramePr>
      <p:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></p:xfrm>
      <a:graphic>
        <a:graphicData uri="{NS_WE}">
          <we:webextensionref r:id="{we_rid}"/>
        </a:graphicData>
      </a:graphic>
    </p:graphicFrame>
  </mc:Choice>
  <mc:Fallback>
    <p:pic>
      <p:nvPicPr>
        <p:cNvPr id="{shape_id}" name={name}/>
        <p:cNvPicPr><a:picLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvPicPr>
        <p:nvPr/>
      </p:nvPicPr>
      <p:blipFill><a:blip r:embed="{pic_rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
      <p:spPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
      </p:spPr>
    </p:pic>
  </mc:Fallback>
</mc:AlternateContent>"""))

    def box(self, rect: dict) -> tuple[Emu, Emu, Emu, Emu]:
        """A live box ({x, y, w, h}: fractions of the slide from its top left) on the slide."""
        cx, cy = self.prs.slide_width, self.prs.slide_height
        return (Emu(round(rect["x"] * cx)), Emu(round(rect["y"] * cy)),
                Emu(round(rect["w"] * cx)), Emu(round(rect["h"] * cy)))

    def add_movie(self, index: int, rect: dict, movie: bytes, mime: str, poster: bytes, name: str):
        """A native video at a box of slide `index`, with the poster as its poster frame: it plays
        in PowerPoint, in the static deck too - no add-in, no server."""
        shape = self.prs.slides[index].shapes.add_movie(BytesIO(movie), *self.box(rect),
                                                         poster_frame_image=BytesIO(poster), mime_type=mime)
        shape.name = name

    def add_link(self, index: int, rect: dict, poster: bytes, url: str, name: str):
        """The poster at a box of slide `index`, a click on it opening `url` in the browser (an
        online video: python-pptx cannot embed PowerPoint's own online video)."""
        pic = self.prs.slides[index].shapes.add_picture(BytesIO(poster), *self.box(rect))
        pic.click_action.hyperlink.address = url
        pic.name = name

    def save(self, path: Path):
        self.prs.save(path)


def retarget(pptx: Path, server: str, key: str | None = None) -> int:
    """Points the live slides of a PPTX at another server: their add-in reference, their
    "server" property and the presenter key they carry (None: none - the slides ask for it).
    Returns how many add-in objects were changed. The file is rewritten in place
    (PowerPoint must not have it open)."""
    target, addin = origin(server), addin_id(server)
    with zipfile.ZipFile(pptx) as z:
        entries = [(info, z.read(info)) for info in z.infolist()]
    changed = 0
    out = []
    for info, data in entries:
        if info.filename.startswith("ppt/webextensions/webextension") and info.filename.endswith(".xml"):
            root = etree.fromstring(data)
            ref = root.find(f"{{{NS_WE}}}reference")
            if ref is not None and ref.get("storeType") == "Registry":
                ref.set("id", addin)
                props = root.find(f"{{{NS_WE}}}properties")
                for p in list(props):
                    if p.get("name") == "server":
                        p.set("value", json.dumps(target))
                    elif p.get("name") == "key":
                        props.remove(p)
                if key:
                    etree.SubElement(props, f"{{{NS_WE}}}property", name="key", value=json.dumps(key))
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                changed += 1
        out.append((info, data))
    tmp = pptx.with_name(pptx.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for info, data in out:
            z.writestr(info, data)
    tmp.replace(pptx)
    return changed
