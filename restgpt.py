from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate, FewShotPromptTemplate
from langchain.llms import OpenAI
from langchain.prompts.example_selector import LengthBasedExampleSelector
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from specification_parser import parse_parameters
from model_properties.examples import *
from model_properties.contexts import *
from config import API_KEY
import json

class Classifications(BaseModel):
    check_operation_constraint: bool = Field(description="""
A boolean that returns True if the input definitively mentions parameters that required or not required.""")
    check_parameter_format: bool = Field(description="""
A boolean that returns True if the input mentions parameter data types or how the parameter is expected to 
be formatted. Data types and formatting can include lists, dates, numbers, emails, binary, ipv6, among others.""")
    check_parameter_constraint: bool = Field(description="""
A boolean that returns True if the input mentions a limitation of the value of the parameter, such as 
a maximum, minimum, or length.""")
    check_parameter_example: bool = Field(description="""
A boolean that returns True if the input mentions values for the parameter which it should relate to.""")

class FewShotModel:
    def __init__(self, examples, prefix, suffix, llm):
        self.examples = examples
        self.prefix = prefix
        self.suffix = suffix
        self.llm = llm

    def run_model(self, input_value):
        examples_format = PromptTemplate(
            input_variables=["input", "output"],
            template="Input: {input}\nOutput: {output}"
        )
        examples_selector = LengthBasedExampleSelector(
            examples=self.examples,
            example_prompt=examples_format,
            max_length="5500" # based on words (~7000 word input limit)
        )
        fewshot_prompt = FewShotPromptTemplate(
            example_prompt=examples_format,
            example_selector=examples_selector,
            example_separator="\n\n",
            prefix=self.prefix,
            suffix=self.suffix,
            input_variables=["input"]
        )
        fewshot_chain = LLMChain(prompt=fewshot_prompt, llm=self.llm)
        return fewshot_chain.run(input_value)

def rule_classification(llm, description):
    output_parser = PydanticOutputParser(
        pydantic_object=Classifications
    )
    classification_prompt = PromptTemplate(
        template=CLASSIFICATION_CONTEXT + "\n{instructions}\nInput: {description}\n",
        input_variables=["description"],
        partial_variables={"instructions": output_parser.get_format_instructions()}
    )
    rule_classifier = LLMChain(
        llm=llm,
        prompt=classification_prompt,
    )
    return rule_classifier.run(description)

def operation_constraint(llm, input_value):
    return FewShotModel(OPERATION_CONSTRAINT_EXAMPLES, OPERATION_CONSTRAINT_CONTEXT, MODEL_SUFFIX, llm).run_model(input_value)

def parameter_format(llm, input_value):
    return FewShotModel(PARAMETER_FORMAT_EXAMPLES, PARAMETER_FORMAT_CONTEXT, MODEL_SUFFIX, llm).run_model(input_value)

def parameter_constraint(llm, input_value):
    return FewShotModel(PARAMETER_CONSTRAINT_EXAMPLES, PARAMETER_CONSTRAINT_CONTEXT, MODEL_SUFFIX, llm).run_model(input_value)

def parameter_example(llm, input_value):
    return FewShotModel(PARAMETER_EXAMPLE_EXAMPLES, PARAMETER_EXAMPLE_CONTEXT, MODEL_SUFFIX, llm).run_model(input_value)

def run_llm_chain(file_path, method_path, method_type):

    llm = OpenAI(model_name="gpt-3.5-turbo", openai_api_key = API_KEY, temperature=0)

    method_key = f"{method_path} {method_type}"
    parameters = parse_parameters(file_path).get(method_key)

    restriction_list = []

    for parameter in parameters:
        operation_constraints = None
        parameter_formats = None
        parameter_constraints = None
        parameter_examples = None
        name = parameter.get("name")
        description = parameter.get("description")
        minimum = parameter.get("minimum")
        maximum = parameter.get("maximum")
        format_value = parameter.get("format")
        type_value = parameter.get("type")
        enum = parameter.get("enum")

        classifications = json.loads(rule_classification(llm, description))
        #print("Attempted for: " + str(parameter))
        #print(classifications)
        if classifications.get("check_operation_constraint"):
            input_value = f"name: {name}\ndescription: {description}"
        #    print("Attempted once with " + str(parameter))
            operation_constraints = operation_constraint(llm, input_value)
        if classifications.get("check_parameter_constraint") and (minimum is None or maximum is None):
        #    print("Attempted paramter constraint with " + str(parameter))
            parameter_constraints = parameter_constraint(llm, description)
        if classifications.get("check_parameter_format") and (format_value is None or type_value is None):
        #    print("Attempted parameter format with " + str(parameter))
            parameter_formats = parameter_format(llm, description)
        if classifications.get("check_parameter_example") and (enum is None):
        #    print("Attempted parameter example with " + str(parameter))
            parameter_examples = parameter_example(llm, description)

        restriction_list.append(
            {"name": name,
            "operational_constraints": operation_constraints,
            "parameter_formats": parameter_formats,
            "parameter_constraints": parameter_constraints,
            "parameter_examples": parameter_examples}
        )
        #print({operation_constraints, parameter_formats, parameter_constraints, parameter_examples})
    return restriction_list

if __name__ == "__main__":
    print(run_llm_chain("specifications/openapi_yaml/spotify.yaml", "/me/playlists", "get"))
