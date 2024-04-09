import { Accordion, Tag } from "@trussworks/react-uswds";
import React from "react";

interface AccordionLabResultsProps {
  title: string;
  abnormalTag: boolean;
  content: React.JSX.Element[];
  organizationId: string;
}

/**
 * Accordion component for displaying lab results.
 * @param props - The props object.
 * @param props.title - The title of the lab result.
 * @param props.abnormalTag - Boolean value if the lab result is abnormal.
 * @param props.content - The content within the accordian.
 * @param props.organizationId - The id of the organization you are getting lab results for.
 * @returns React element representing the AccordionLabResults component.
 */
export const AccordionLabResults: React.FC<AccordionLabResultsProps> = ({
  title,
  abnormalTag,
  content,
  organizationId,
}: AccordionLabResultsProps): React.JSX.Element => {
  return (
    <Accordion
      items={[
        {
          title: (
            <>
              {title}
              {abnormalTag && (
                <Tag background={"#B50909"} className={"margin-left-105"}>
                  Abnormal
                </Tag>
              )}
            </>
          ),
          content: content,
          expanded: true,
          id: title,
          headingLevel: "h5",
          className: `${organizationId}_acc_item`,
        },
      ]}
      className={`accordion-rr ${organizationId}_accordion margin-bottom-3`}
    />
  );
};
