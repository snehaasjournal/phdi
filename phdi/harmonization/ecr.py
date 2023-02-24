from lxml import etree
import json

from pathlib import Path

ecr_file_name = "jsonified_CDA_eICR.xml"
rr_file_name = "jsonified_CDA_RR.xml"

ecr = json.loads(Path("jsonified_CDA_eICR.xml").read_text())
rr = json.loads(Path("jsonified_CDA_RR.xml").read_text())

ecr = etree.fromstring(ecr)
rr = etree.fromstring(rr)
rr_tags = ["templateId", "id", "code", "title", "effectiveTime", "confidentialityCode"]
rr_tags = ["{urn:hl7-org:v3}" + tag for tag in rr_tags]
rr_elements = []
for element in rr:
    if element.tag in rr_tags:
        rr_elements.append(element)
    elif element.tag == "{urn:hl7-org:v3}component":
        print("temp")

rr[14]