import json
from pathlib import Path
import click


@click.command()
@click.option(
    "-i",
    "--inputFile",
    type=str,
    help="File to be jsonified",
    required=True,
)
@click.option(
    "-o",
    "--outputPath",
    type=str,
    default="",
    show_default=True,
    help="The location of the output file",
)
@click.option(
    "-p",
    "--printOutput",
    type=bool,
    help="Print the jsonified contents of the input file to the console.",
    default=False,
    show_default=True,
)
def jsonify(
    inputfile: str,
    outputpath: str,
    printoutput: bool,
):
    """
    Jsonify File is a simple CLI utility to produced a jsonified version of the contents
    of a text file.
    """

    # Read input
    input_file = Path(inputfile)
    input_text = input_file.read_text()

    # jsonify
    jsonified_text = json.dumps(input_text)

    # Write jsonified to file
    if outputpath != "":
        output_path = Path(outputpath)
        output_path = output_path / f"jsonified_{input_file.name}"
        output_file = open(output_path, "w")
        output_file.write(jsonified_text)
        output_file.close()

    # Print jsonified contents
    if printoutput is True:
        print(jsonified_text)


if __name__ == "__main__":
    jsonify()
