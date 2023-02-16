# PHDI Azure ReadSourceData Container

This Docker container provides a simple API for reading source data from an Azure storage account and parsing into individual messages for processing in a pipeline. It should be deployed as part of a full pipeline using PHDI Building Blocks as in [CDCgov/phdi-azure](https://github.com/CDCgov/phdi-azure).

## Usage

This service is meant to be deployed as part of a full pipeline using PHDI Building Blocks as in [CDCgov/phdi-azure](https://github.com/CDCgov/phdi-azure). It responds to an EventGrid subscription on blob creation events.