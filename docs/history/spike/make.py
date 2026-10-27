"""Spike S1: write the probe add-in manifest and a PPTX whose slides embed the add-in.

Usage: python make.py [origin]   (default http://localhost:8471)
"""
import json
import sys
import uuid
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import quoteattr

from lxml import etree
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.util import Emu

HERE = Path(__file__).parent
ADDIN_ID = "8a4b6f2e-3c1d-4e5f-9a7b-2c3d4e5f6a70"
ADDIN_VERSION = "1.0.0.0"

RT_WEBEXT = "http://schemas.microsoft.com/office/2011/relationships/webextension"
CT_WEBEXT = "application/vnd.ms-office.webextension+xml"
NS_WE = "http://schemas.microsoft.com/office/webextensions/webextension/2010/11"


def manifest(origin: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
           xsi:type="ContentApp">
  <Id>{ADDIN_ID}</Id>
  <Version>{ADDIN_VERSION}</Version>
  <ProviderName>texquiz</ProviderName>
  <DefaultLocale>en-US</DefaultLocale>
  <DisplayName DefaultValue="texquiz probe"/>
  <Description DefaultValue="Spike: reports content add-in lifecycle events."/>
  <IconUrl DefaultValue="{origin}/icon-32.png"/>
  <HighResolutionIconUrl DefaultValue="{origin}/icon-64.png"/>
  <SupportUrl DefaultValue="{origin}/"/>
  <AppDomains>
    <AppDomain>{origin}</AppDomain>
  </AppDomains>
  <Hosts>
    <Host Name="Presentation"/>
  </Hosts>
  <DefaultSettings>
    <SourceLocation DefaultValue="{origin}/probe.html"/>
    <RequestedWidth>640</RequestedWidth>
    <RequestedHeight>360</RequestedHeight>
  </DefaultSettings>
  <Permissions>ReadDocument</Permissions>
  <AllowSnapshot>true</AllowSnapshot>
</OfficeApp>
"""


def slide_png(text: str, colour: str) -> bytes:
    im = Image.new("RGB", (1920, 1080), colour)
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype("arial.ttf", 160)
    d.text((960, 540), text, fill="black", font=font, anchor="mm")
    d.text((960, 900), "static slide image (LaTeX stand-in)", fill="black",
           font=ImageFont.truetype("arial.ttf", 48), anchor="mm")
    small = ImageFont.truetype("arial.ttf", 18)
    for row in range(4):  # fine detail to judge sharpness: small text and a 1-px grating
        d.text((40, 40 + 30 * row), "The quick brown fox jumps over the lazy dog 0123456789", fill="black", font=small)
    for x in range(40, 640, 2):
        d.line([(x, 170), (x, 230)], fill="black")
    buf = BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def webextension_xml(props: dict, snapshot_rid: str) -> bytes:
    # Office.js document settings are stored JSON-encoded in we:property/@value.
    prop_xml = "".join(f"<we:property name={quoteattr(k)} value={quoteattr(json.dumps(v))}/>"
                       for k, v in props.items())
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<we:webextension xmlns:we="{NS_WE}" id="{{{str(uuid.uuid4()).upper()}}}">'
            f'<we:reference id="{ADDIN_ID}" version="{ADDIN_VERSION}" store="developer" storeType="Registry"/>'
            f'<we:alternateReferences/>'
            f'<we:properties>{prop_xml}</we:properties>'
            f'<we:bindings/>'
            f'<we:snapshot xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="{snapshot_rid}"/>'
            f'</we:webextension>').encode("utf-8")


def add_webextension(slide, prs, n: int, props: dict, snapshot_png: bytes):
    pkg = prs.part.package
    part = Part(PackURI(f"/ppt/webextensions/webextension{n}.xml"), CT_WEBEXT, pkg, b"")
    image_part = pkg.get_or_add_image_part(BytesIO(snapshot_png))
    snap_rid = part.relate_to(image_part, RT.IMAGE)
    part._blob = webextension_xml(props, snap_rid)
    we_rid = slide.part.relate_to(part, RT_WEBEXT)
    fallback_rid = slide.part.relate_to(image_part, RT.IMAGE)

    tree = slide.shapes._spTree
    shape_id = max(int(x) for x in tree.xpath("//p:cNvPr/@id")) + 1
    cx, cy = prs.slide_width, prs.slide_height
    name = f"texquiz {props.get('slide')}"
    xml = f"""
<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
    xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
    xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <mc:Choice xmlns:we="{NS_WE}" Requires="we">
    <p:graphicFrame>
      <p:nvGraphicFramePr>
        <p:cNvPr id="{shape_id}" name="{name}"/>
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
        <p:cNvPr id="{shape_id}" name="{name}"/>
        <p:cNvPicPr><a:picLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvPicPr>
        <p:nvPr/>
      </p:nvPicPr>
      <p:blipFill><a:blip r:embed="{fallback_rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
      <p:spPr>
        <a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
      </p:spPr>
    </p:pic>
  </mc:Fallback>
</mc:AlternateContent>"""
    tree.append(etree.fromstring(xml))


def build(path: Path):
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    blank = prs.slide_layouts[6]
    plan = [("1 plain", "#e0e0e0", False), ("2 add-in", "#cfe8ff", True), ("3 add-in", "#d8f5d0", True),
            ("4 plain", "#e0e0e0", False), ("5 add-in", "#ffe0cc", True)]
    n = 0
    for label, colour, live in plan:
        slide = prs.slides.add_slide(blank)
        png = slide_png(label, colour)
        (HERE / "www" / f"slide{len(prs.slides)}.png").write_bytes(png)
        slide.shapes.add_picture(BytesIO(png), 0, 0, prs.slide_width, prs.slide_height)
        slide.notes_slide.notes_text_frame.text = f"notes for {label}"
        if live:
            n += 1
            idx = len(prs.slides)
            add_webextension(slide, prs, n,
                             {"slide": idx, "quiz": f"q{idx}", "phase": "question",
                              "json": {"nested": [1, 2], "s": "ä\"<&>"}},
                             png)
    prs.save(path)
    return [s.slide_id for s in prs.slides]


if __name__ == "__main__":
    origin = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8471"
    www = HERE / "www"
    www.mkdir(exist_ok=True)
    (HERE / "manifest.xml").write_text(manifest(origin), encoding="utf-8")
    for size in (32, 64):
        Image.new("RGB", (size, size), "#e21b3c").save(www / f"icon-{size}.png")
    ids = build(HERE / "probe.pptx")
    print("manifest.xml, probe.pptx written; slide ids", ids)
