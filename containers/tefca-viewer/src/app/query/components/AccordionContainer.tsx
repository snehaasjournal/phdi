import Demographics from "./Demographics";
import ObservationTable from "./ObservationTable";
import EncounterTable from "./EncounterTable";
import DiagnosticReportsTable from "./DiagnosticReportsTable";
import React from "react";
import { Accordion } from "@trussworks/react-uswds";
import { formatString } from "@/app/format-service";
import {
  AccordianSection,
  AccordianH4,
  AccordianDiv,
} from "../component-utils";
import { UseCaseQueryResponse } from "@/app/query-service";
import ConditionsTable from "./ConditionsTable";

type AccordionContainerProps = {
  queryResponse: UseCaseQueryResponse;
};

/**
 * Returns the Accordion component to render all components of the query response.
 * @param props - The props for the AccordionContainer component.
 * @param props.queryResponse - The response from the query service.
 * @returns The AccordionContainer component.
 */
const AccordianContainer: React.FC<AccordionContainerProps> = ({
  queryResponse,
}) => {
  console.log("queryResponse:", queryResponse);
  const accordionItems: any[] = [];

  const patient =
    queryResponse.patients && queryResponse.patients.length === 1
      ? queryResponse.patients[0]
      : null;
  const observations = queryResponse.observations
    ? queryResponse.observations
    : null;
  const encounters = queryResponse.encounters ? queryResponse.encounters : null;
  const conditions = queryResponse.conditions ? queryResponse.conditions : null;
  const diagnosticReports = queryResponse.diagnosticReports
    ? queryResponse.diagnosticReports
    : null;

  if (patient) {
    accordionItems.push({
      title: "Patient Info",
      content: (
        <>
          <AccordianSection>
            <AccordianH4>
              <span id="patient">Demographics</span>
            </AccordianH4>
            <AccordianDiv>
              <Demographics patient={patient} />
            </AccordianDiv>
          </AccordianSection>
        </>
      ),
      expanded: true,
      headingLevel: "h3",
    });
  }

  if (observations) {
    accordionItems.push({
      title: "Observations",
      content: (
        <>
          <AccordianSection>
            <AccordianH4>
              <span id="observations">Observations</span>
            </AccordianH4>
            <AccordianDiv>
              <ObservationTable observations={observations} />
            </AccordianDiv>
          </AccordianSection>
        </>
      ),
      expanded: true,
      headingLevel: "h3",
    });
  }

  if (encounters) {
    accordionItems.push({
      title: "Encounters",
      content: (
        <>
          <AccordianSection>
            <AccordianH4>
              <span id="encounters">Encounters</span>
            </AccordianH4>
            <AccordianDiv>
              <EncounterTable encounters={encounters} />
            </AccordianDiv>
          </AccordianSection>
        </>
      ),
      expanded: true,
      headingLevel: "h3",
    });
  }

  if (conditions) {
    accordionItems.push({
      title: "Conditions",
      content: (
        <>
          <AccordianSection>
            <AccordianH4>
              <span id="conditions">Conditions</span>
            </AccordianH4>
            <AccordianDiv>
              <ConditionsTable conditions={conditions} />
            </AccordianDiv>
          </AccordianSection>
        </>
      ),
      expanded: true,
      headingLevel: "h3",
    });
  }

  if (diagnosticReports) {
    accordionItems.push({
      title: "Diagnostic Reports",
      content: (
        <>
          <AccordianSection>
            <AccordianH4>
              <span id="diagnosticReports">Diagnostic Reports</span>
            </AccordianH4>
            <AccordianDiv>
              <DiagnosticReportsTable diagnosticReports={diagnosticReports} />
            </AccordianDiv>
          </AccordianSection>
        </>
      ),
      expanded: true,
      headingLevel: "h3",
    });
  }

  //Add id, adjust title
  accordionItems.forEach((item, index) => {
    let formattedTitle = formatString(item["title"]);
    item["id"] = `${formattedTitle}_${index + 1}`;
    item["title"] = <span id={formattedTitle}>{item["title"]}</span>;
    accordionItems[index] = item;
  });

  return (
    <Accordion
      className="info-container"
      items={accordionItems}
      multiselectable={true}
    />
  );
};
export default AccordianContainer;
