/**
 * @jest-environment node
 */
import {
  DockerComposeEnvironment,
  StartedDockerComposeEnvironment,
} from "testcontainers";
import fs from "fs";
import YAML from "yaml";

describe("s3 api", () => {
  let dockerContainers: StartedDockerComposeEnvironment;
  const bundle = {
    entry: [
      {
        resource: {
          id: "1234",
        },
      },
    ],
  };
  const fhirPathFile = fs
    .readFileSync("./src/app/api/fhirPath.yml", "utf8")
    .toString();
  const fhirPathMappings = YAML.parse(fhirPathFile);
  beforeAll(async () => {
    const composeFile = "docker-compose-s3.yml";
    dockerContainers = await new DockerComposeEnvironment(
      "./",
      composeFile,
    ).up();
  }, 60000);
  afterAll(async () => {
    await dockerContainers.stop();
  });

  it("should save file to s3", async () => {
    const resp = await fetch("http://localhost:3000/api/save-fhir-data", {
      body: `{ "fhirBundle": ${JSON.stringify(bundle)}, 
      "saveSource":"s3"
      }`,
      method: "POST",
    });

    const actualRespBody = await resp.json();
    expect(resp.status).toBe(200);
    expect(actualRespBody.message).toBe(
      "Success. Saved FHIR Bundle to S3: 1234",
    );
  }, 60000);

  it("should get file from s3", async () => {
    await fetch("http://localhost:3000/api/save-fhir-data", {
      body: `{ "fhirBundle": ${JSON.stringify(bundle)}, 
      "saveSource":"s3"
      }`,
      method: "POST",
    });

    const resp = await fetch("http://localhost:3000/api/fhir-data?id=1234");

    const actualRespBody = await resp.json();
    expect(resp.status).toBe(200);
    expect(actualRespBody.fhirBundle).toEqual(bundle);
    expect(actualRespBody.fhirPathMappings).toEqual(fhirPathMappings);
  }, 60000);
});
