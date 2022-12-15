import os
import requests
import subprocess
import json
import phdi.fhir.transport
import pathlib
import shutil
import click


@click.command()
@click.option(
    "-sv",
    "--syntheaVersion",
    default="v3.1.1",
    type=str,
    help="The version of Synthea to use",
    show_default=True
)
@click.option(
    "-u", "--upload", default=True, type=bool, help="Upload data to a FHIR server", show_default=True
)
@click.option(
    "-fu",
    "--fhirUrl",
    default="http://localhost:8080",
    type=str,
    help="URL of the FHIR server that data is uploaded to",
    show_default=True
)
@click.option("-s", "--seed", default=1, type=int, help="Synthea seed", show_default=True)
@click.option(
    "-p",
    "--populationSize",
    default=100,
    type=str,
    help="Synthea patient population size",
    show_default=True
)
@click.option("-cs", "--clinicianSeed", default=1, type=int, help="clinician seed", show_default=True)

def generate_and_load_synthea_data(
    syntheaversion: str,
    upload: bool,
    fhirurl: str,
    seed: int,
    populationsize: int,
    clinicianseed: int,
):
    """
    Generate and Load Synthea is a simple CLI utility for generating synthetic FHIR data
    with Synthea and uploading it to a FHIR sever. Specifying the Synthea version and
    seed values allow for FHIR datasets to be reproduced.

    """

    # Prepare Synthea directory.
    synthea_directory = pathlib.Path.home() / "synthea"
    if not synthea_directory.is_dir():
        synthea_directory.mkdir()
    if not (synthea_directory / syntheaversion).is_dir():
        (synthea_directory / syntheaversion).mkdir()

    # Download the synthea jar file
    synthea_directory = synthea_directory / syntheaversion
    if not (synthea_directory / "synthea-with-dependencies.jar").is_file():
        print("Downloading synthea-with-dependencies.jar to...")
        synthea_url = f"https://github.com/synthetichealth/synthea/releases/download/{syntheaversion}/synthea-with-dependencies.jar"
        synthea_jar_response = requests.get(synthea_url, stream=True)
        with open(synthea_directory / "synthea-with-dependencies.jar", "wb") as file:
            for chunk in synthea_jar_response.iter_content(chunk_size=1024):
                file.write(chunk)

    # Create Synthea data
    synthea_args = ["java", "-jar", "synthea-with-dependencies.jar"]
    synthea_command_arguments = ["-p", str(populationsize), "-s", str(seed), '-cs', str(clinicianseed)]
    synthea_args.extend(synthea_command_arguments)
    print(synthea_args)
    dataset_directory = (
        synthea_directory / "datasets" / "".join(synthea_command_arguments)
    )
    if dataset_directory.is_dir():
        print(
            f"A Synthea dataset with arguments {' '.join(synthea_command_arguments)} already exists in {dataset_directory}."
        )
    else:
        print(
            f"Generating Synthea dataset with arguments: {' '.join(synthea_command_arguments)}"
        )
        dataset_directory.mkdir(parents=True)
        subprocess.run(args=synthea_args, cwd=synthea_directory)
        shutil.copytree(
            synthea_directory / "output" / "fhir", dataset_directory / "fhir"
        )
        shutil.copytree(
            synthea_directory / "output" / "metadata", dataset_directory / "metadata"
        )
        shutil.rmtree(synthea_directory / "output")

    # Upload to FHIR server
    if upload is True:
        print(f"Uploading data to a FHIR server located at {fhirurl}...")
        base_path = dataset_directory / "fhir"
        fhir_files = os.listdir(base_path)
        fhir_files.sort(reverse=True)
        for fhir_filename in fhir_files:
            fhir_filepath = os.path.join(base_path, fhir_filename)
            print(f"Evaluating {fhir_filepath}")

            if os.path.isfile(fhir_filepath) and fhir_filepath.endswith(".json"):
                with open(fhir_filepath) as fhir_file:
                    print(f"Importing {fhir_filepath}")
                    phdi.fhir.transport.http.http_request_with_reauth(
                        cred_manager=None,
                        url=f"{fhirurl}/fhir",
                        retry_count=3,
                        request_type="POST",
                        allowed_methods="POST",
                        headers={},
                        data=json.load(fhir_file),
                    )


if __name__ == "__main__":
    generate_and_load_synthea_data()
