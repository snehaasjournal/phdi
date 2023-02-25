from lxml import etree
from io import StringIO
import json

from pathlib import Path

ecr_file_name = "jsonified_CDA_eICR.xml"
rr_file_name = "jsonified_CDA_RR.xml"

ecr = json.loads(Path(ecr_file_name).read_text())
rr = json.loads(Path(rr_file_name).read_text())

#ecr = etree.fromstring(ecr)
rr = etree.fromstring(rr)

rr_tags = ["templateId", "id", "code", "title", "effectiveTime", "confidentialityCode"]
rr_elements = []
for tag in rr_tags:
    rr_elements.append(rr.find(f"./{tag}", namespaces=rr.nsmap))

breakpoint()
