from distutils.log import INFO
import os
import requests
import subprocess
import json
import phdi.fhir.transport
import pathlib
import shutil
import click
import docker
from time import sleep
import polling2
import requests
import urllib3
import logging


@click.command()
@click.option(
    "-sv",
    "--synthea_version",
    default="v3.1.1",
    type=str,
    help="The version of Synthea to use",
    show_default=True,
)
@click.option(
    "-u",
    "--upload",
    default=True,
    type=bool,
    help="Upload data to a FHIR server",
    show_default=True,
)
@click.option(
    "-ss",
    "--start_server",
    default=False,
    type=bool,
    help="Start an instance of the HAPI FHIR server on localhost. By default the latest"
    " version is used, other versions may be specified with --hapi_version. By default "
    "the server is started on locahost:8080, other ports may be specified with "
    "--server_port.",
    show_default=True,
)
@click.option(
    "-sp",
    "--server_port",
    default="8080",
    type=int,
    help="The port on localhost where an instance of the HAPI FHIR server will be started.",
    show_default=True,
)
@click.option(
    "-hv",
    "--hapi_version",
    default="latest",
    type=str,
    help="The version of the HAPI FHIR server that will be started.",
    show_default=True,
)
@click.option(
    "-fu",
    "--fhir_url",
    default="http://localhost:8080",
    type=str,
    help="URL of the FHIR server that data is uploaded to",
    show_default=True,
)
@click.option(
    "-s", "--seed", default=1, type=int, help="Synthea seed", show_default=True
)
@click.option(
    "-p",
    "--population_size",
    default=100,
    type=str,
    help="Synthea patient population size",
    show_default=True,
)
@click.option(
    "-cs",
    "--clinician_seed",
    default=1,
    type=int,
    help="clinician seed",
    show_default=True,
)
@click.option(
    "--generate_only_alive_patients",
    default="true",
    type=str,
    help="Only generate patients that are alive.",
    show_default=True,
)
def generate_and_load_synthea_data(
    synthea_version: str,
    upload: bool,
    start_server: bool,
    server_port: int,
    hapi_version: str,
    fhir_url: str,
    seed: int,
    population_size: int,
    clinician_seed: int,
    generate_only_alive_patients: str,
):
    """
    Generate and Load Synthea is a simple CLI utility for generating synthetic FHIR data
    with Synthea, and uploading it to a FHIR sever. The Synthea version and
    seed values are controlled to ensure FHIR dataset reproducibility. Datasets
    generated with this tool are stored locally in the HOME/synthea/ directory. If a
    specific dataset is requested that already exists it will not be recreated, instead
    the existing data will be used. If you do not already have a FHIR server running,
    Generate and Load Synthea supports spinning up an instance of the HAPI FHIR server
    on localhost with Docker (see options below).  

    """

    # Prepare Synthea directory.
    synthea_directory = pathlib.Path.home() / "synthea"
    if not synthea_directory.is_dir():
        synthea_directory.mkdir()
    if not (synthea_directory / synthea_version).is_dir():
        (synthea_directory / synthea_version).mkdir()

    # Download the synthea jar file
    synthea_directory = synthea_directory / synthea_version
    if not (synthea_directory / "synthea-with-dependencies.jar").is_file():
        print("Downloading synthea-with-dependencies.jar to...")
        synthea_url = f"https://github.com/synthetichealth/synthea/releases/download/{syntheaversion}/synthea-with-dependencies.jar"
        synthea_jar_response = requests.get(synthea_url, stream=True)
        with open(synthea_directory / "synthea-with-dependencies.jar", "wb") as file:
            for chunk in synthea_jar_response.iter_content(chunk_size=1024):
                file.write(chunk)

    # Create Synthea data
    synthea_args = ["java", "-jar", "synthea-with-dependencies.jar"]
    synthea_command_arguments = [
        "-p",
        str(population_size),
        "-s",
        str(seed),
        "-cs",
        str(clinician_seed),
        f"--generate.only_alive_patients={generate_only_alive_patients}",
    ]
    synthea_args.extend(synthea_command_arguments)
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

    # Start HAPI FHIR server:
    if start_server is True:
        docker_client = docker.from_env()
        docker_client.images.pull(f"hapiproject/hapi:{hapi_version}")
        hapi_server = docker_client.containers.run(
            f"hapiproject/hapi:{hapi_version}", ports={"8080": server_port}, detach=True
        )
        fhir_url = f"http://localhost:{server_port}"

        print("Waiting for the HAPI FHIR server to start...")
        # Wait for container to start.
        while hapi_server.status != "running":
            sleep(1)
            hapi_server.reload()
            continue
        
        # Poll the /fhir/metdata endpoint untill a 200 is returned to determine that 
        # the server is up and running.
        polling2.poll(
            lambda: requests.get(fhir_url + "/fhir/metadata").status_code == 200,
            step=5,
            ignore_exceptions=(
                urllib3.exceptions.ProtocolError,
                requests.exceptions.ConnectionError,
            ),
            poll_forever=True,
        )
        print(f"HAPI FHIR server started on {fhir_url}.")

    # Upload to FHIR server
    if upload is True:
        print(f"Uploading data to a FHIR server located at {fhir_url}...")
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
                        url=f"{fhir_url}/fhir",
                        retry_count=3,
                        request_type="POST",
                        allowed_methods="POST",
                        headers={},
                        data=json.load(fhir_file),
                    )


if __name__ == "__main__":
    generate_and_load_synthea_data()
