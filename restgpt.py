import sys

import openai.error
from src.specification_builder import SpecificationBuilder
from src.report_builder import ReportBuilder
from configurations import RUN_MODE
import argparse
import os
import json
import csv

def build_all_reports():
    original_files = ["rest-countries", "omdb", "language-tool", "spotify", "youtube", "genome-nexus", "ohsome", "fdic", "ocvn"]
    files = ["genome-nexus"]
    for file in files:
        print("Buidling specification for " + file)
        report_builder = ReportBuilder(f'specifications/openapi_yaml/{file}.yaml', f'{file}_results.json')
        report_builder.path_builder()
        report_builder.save_report_to_file()

def build_one_report(file_path, file_name):
    output_name = f"{file_name}_results.json"
    #report_builder = ReportBuilder(file_path, output_name)
    #report_builder.path_builder()
    #report_builder.save_report_to_file()
    spec_build = SpecificationBuilder(file_path, output_name)
    spec_build.build_specification()

def build_all_specs(file_type):
    original_files = ["rest-countries", "omdb", "language-tool", "spotify", "youtube", "genome-nexus", "ohsome", "fdic", "ocvn"]
    files = ["rest-countries", "omdb", "language-tool", "spotify", "youtube", "genome-nexus", "ohsome", "fdic", "ocvn"]
    for file in files:
        print("Buidling specification for " + file)
        spec_builder = SpecificationBuilder(f'src/specifications/openapi_yaml/{file}.yaml', f'src/outputs/{file}_results.{file_type}')
        print("Initialized SpecificationBuilder.")
        spec_builder.build_specification()

def build_one_spec(file_path, file_name):
    output_name = f"src/outputs/{file_name}_results.json"
    spec_build = SpecificationBuilder(file_path, output_name)
    spec_build.build_specification()

def build_all_specs_eval(file_type):
    try:
        files = os.listdir("src/specifications/inputs")
        for file in files:
            file_name = file.split(".")[0]
            print("Buidling specification for " + file_name + ".")
            try:
                spec_builder = SpecificationBuilder(f'src/specifications/inputs/{file}', f'src/outputs/{file_name}_results.{file_type}')
                print("Initialized SpecificationBuilder.")
                spec_builder.build_specification()
            except ImportError:
                print("The config file containing your API key does not exist.")
                return
            except KeyError or openai.error.AuthenticationError:
                print("The API key used to access GPT-3.5 Turbo is invalid.")
                return
            except Exception:
                print(f"Failed to build specification for {file_name}.")
    except Exception:
        print("Failed to access input specifications.")

def build_one_spec_with_report(file_path, file_name):
    # language tool to test requestBody
    # omdb to test general

    output_path = f"src/outputs/{file_name}_results.json"
    spec_build = SpecificationBuilder(file_path, output_path)
    spec_build.build_specification_with_report(f"results/reports_update_512/{file_name}_results.json")

def build_all_specs_with_reports(output_type): # run this for RESTGPT paper enhanced specification generation
    if output_type != "yaml" or output_type != "json":
        output_type = "json" # default json

    original_files = ["rest-countries", "omdb", "language-tool", "spotify", "youtube", "genome-nexus", "ohsome", "fdic",
                      "ocvn"]
    files = ["rest-countries", "omdb", "language-tool", "spotify", "youtube", "genome-nexus", "ohsome", "fdic", "ocvn"]
    for file in files:
        print("Building enhanced specifictaion for " + file)
        spec_builder = SpecificationBuilder(f'specifications/openapi_{output_type}/{file}.{output_type}', f'outputs/openapi_{output_type}/{file}_results.{output_type}')
        spec_builder.build_specification_with_report(f"results/reports_update_512/{file}_results.json")

def build_openai_csv():
    original_files = ["rest-countries", "omdb", "language-tool", "spotify", "youtube", "genome-nexus", "ohsome", "fdic",
                      "ocvn"]
    files = ["rest-countries", "omdb", "language-tool", "spotify", "youtube", "genome-nexus", "ohsome", "fdic",
                      "ocvn"]
    for file in files:
        spec_builder = SpecificationBuilder(f'specifications/openapi_yaml/{file}.yaml')

        file_path = f"results/reports_tokens256_temp0.2/{file}_results.json"
        responses = spec_builder.generate_llm_query_objects(file_path)

        file_name = f"csv/{file}.csv"
        directory = os.path.dirname(file_name)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(file_name, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            # add the header
            writer.writerow(['parameter', 'temperature', 'token_limit', 'prompt', 'response'])

            for response in responses:
                writer.writerow([response.parameter, response.temperature, response.token_limit, response.prompt,
                                 response.response])

def docker_execute():
    # use Docker environment variable when running the container
    file_type = os.getenv("FILETYPE", "json")  # default json
    file_type = "yaml" if file_type == "yaml" else "json"

    build_all_specs_eval(file_type)  # uses the eval folder for the Docker containers

def predefined_inputs(file_type):
    build_all_specs(file_type)

def custom_inputs(file_type):
    build_all_specs_eval(file_type)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RESTGPT')
    parser.add_argument("FILE_TYPE", help="The type of file to output. Choose between 'yaml' and 'json'.")
    file_type = parser.parse_args().FILE_TYPE

    if file_type not in ["yaml", "json"]:
        print("Invalid file type. Choose between 'yaml' and 'json'.")
        sys.exit()

    if RUN_MODE == "predefined":
        predefined_inputs(file_type)
    elif RUN_MODE == "docker":
        docker_execute()
    elif RUN_MODE == "custom":
        custom_inputs(file_type)
    else:
        print("Invalid RUN_MODE. Choose between 'predefined', 'docker', and 'custom'.")
        sys.exit()

    print("RESTGPT Completed!")
    # docker_execute()
    # predefined_inputs("yaml")
    # custom_inputs("yaml") # change the file_type to your choosing

    # build_openai_csv()
    #build_all_specs_with_reports("json")





