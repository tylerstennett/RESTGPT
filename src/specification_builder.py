from llm import run_llm_chain
from prance import ResolvingParser, BaseParser
from parsers.parameter_constraint_parser import ParameterConstraintParser
from parsers.example_parser import ExampleParser
from parsers.parameter_format_parser import ParameterFormatParser
from parsers.specification_parser import parse_parameters
from parsers.ipd_parser import InterDependencyParser
import yaml
import json
import os

class SpecificationBuilder:
    def __init__(self, read_path, output_path):
        self.ipd_parser = InterDependencyParser()
        self.example_parser = ExampleParser()
        self.parameter_constraint_parser = ParameterConstraintParser()
        self.parameter_format_parser = ParameterFormatParser()
        self.output_builder = ResolvingParser(read_path, strict=False).specification #reads in the specification as a dictionary, this is the spec we modify
        self.read_path = read_path
        self.output_path = output_path
        self.paths = []
        valid_http_methods = {'put', 'post', 'patch', 'get', 'delete', 'options', 'head', 'patch', 'trace'}
        for path, path_values in self.output_builder.get('paths', {}).items():
            for method_type, method_values in path_values.items(): # Determine HTTP method
                if method_type in valid_http_methods:
                    method_key_tuple = (path, method_type)
                    self.paths.append(method_key_tuple)
        self.parsed_parameters = parse_parameters(self.read_path)
        self.method_parameter_set = {}
        for method_key, value_list in self.parsed_parameters.items():
            self.method_parameter_set[method_key] = []
            for parameter in value_list:
                if parameter["specifier"] == "parameter":
                    self.method_parameter_set[method_key].append(parameter["name"])
        for method_key in self.parsed_parameters.keys():
            self.method_parameter_set[method_key] = set(self.method_parameter_set[method_key])
        self.report = {}
        self.values_to_add = set(['examples', 'x-dependencies'])
    def _convert_key(self, path):
        return f'{path[0]} {path[1]}'
        
    def _add_parameter_constraint(self, build_parameter, parameter_constraint):
        if parameter_constraint is None:
            return
        for constraint_key, constraint in parameter_constraint.items():
            if  constraint is not None and constraint.strip() != "None":
                build_parameter[constraint_key] = constraint
    def _add_ipd_constraint(self, build_parameter, ipd_constraint):
        if ipd_constraint is None:
            return
        for constraint in ipd_constraint:
            build_parameter["x-dependencies"] = ipd_constraint[constraint]
    def _add_example_values(self, build_parameter, model_examples):
        if model_examples is None: 
            return
        example_key = "examples"
        build_parameter[example_key] = model_examples
    def _add_parameter_type_values(self, build_parameter, parameter_types):
        if parameter_types is None: 
            return None
        for type_key, extracted_type in parameter_types.items():
            if extracted_type.strip() != "None":
                if type_key == "items" or type_key == "collectionFormat":
                    if parameter_types["type"] == "array":
                        build_parameter[type_key] = extracted_type
                else:
                    build_parameter[type_key] = extracted_type    

    def process_operation(self, path, method): 
        operation = None
        if path in self.output_builder['paths']: 
            if method in self.output_builder['paths'][path]:
                operation = self.output_builder['paths'][path][method]
        if operation is None:
            raise Exception("Operation not found")
        parameters = None 
        #x-dependencies are operation level
        xdependencies = [] 
        request_body = None
        if 'x-dependencies' in operation:
            xdependencies = operation['x-dependencies']
        if 'parameters' in operation:
            parameters = operation['parameters']
        if 'requestBody' in operation: 
            request_body = True
        generated_parameter_values, generated_request_body_values = self.model_constraints(path, method)
        if parameters:
            for parameter in parameters: 
                self.process_parameter(parameter, generated_parameter_values, xdependencies)
        if request_body:
            self.process_request_body(operation['requestBody'], generated_request_body_values, xdependencies)
        if xdependencies: 
            operation['x-dependencies'] = xdependencies
        #with open('test.yaml', 'w') as yaml_file:
        #    yaml.dump(self.output_builder, yaml_file, default_flow_style=False, sort_keys=False)

    def process_parameter(self, parameter, generated_parameter_values, xdependencies):
        if parameter['name'] in generated_parameter_values:
                constraint_set = generated_parameter_values[parameter['name']]
                if 'name' in constraint_set:
                    constraint_set.pop("name")
                parameter['examples'] = {} if 'examples' not in parameter else parameter['examples']  
                if 'examples' in constraint_set:
                    for key in constraint_set['examples']['examples']:
                        parameter['examples'][key] = constraint_set['examples']['examples'][key]
                    constraint_set.pop("examples")
                if 'x-dependencies' in constraint_set:
                    xdependencies.extend(constraint_set['x-dependencies'])
                    constraint_set.pop("x-dependencies")
                if 'schema' not in parameter: 
                    parameter['schema'] = {}
                if 'type' in constraint_set:
                    schema_loc = parameter['schema']
                    if constraint_set['type'] == 'array':
                        schema_loc.setdefault("items", {})
                        if constraint_set.get("items") is not None and constraint_set.get("items").strip() != "None":
                            schema_loc['items'].setdefault("type", constraint_set.get("items"))
                        if constraint_set.get("format") is not None and constraint_set.get("format").strip() != "None":
                            schema_loc['items'].setdefault("format", constraint_set.get("format"))
                    else:
                        schema_loc.setdefault("type", constraint_set.get("type"))
                    constraint_set.pop("type")
                for field in constraint_set:
                    parameter['schema'].setdefault(field, constraint_set.get(field))
                
    def process_request_body(self, request_body, generated_request_body_values, xdependencies):
        encoding_type = None
        for encoding in request_body.get("content", {}):
                if encoding != 'description':
                    encoding_type = encoding
                    break
        if encoding_type: 
            if 'schema' in request_body['content'][encoding_type]:
                if 'properties' in request_body['content'][encoding_type]['schema']:
                    for property_name in request_body['content'][encoding_type]['schema']['properties']:
                        constraint_set = None
                        for item in generated_request_body_values:
                            if isinstance(item, dict) and 'name' in item and property_name == item['name']:
                                constraint_set = item 
                        if constraint_set:
                            if 'name' in constraint_set:
                                constraint_set.pop("name")
                            if 'examples' in constraint_set:
                                request_body['content'][encoding_type]['schema']['properties'][property_name].setdefault("examples", {})
                                for key in constraint_set['examples']['examples']:
                                    request_body['content'][encoding_type]['schema']['properties'][property_name]['examples'][key] = constraint_set['examples']['examples'][key]
                                constraint_set.pop("examples")
                            if 'x-dependencies' in constraint_set:
                                xdependencies.extend(constraint_set['x-dependencies'])
                                constraint_set.pop("x-dependencies")
                            if 'type' in constraint_set:
                                if constraint_set['type'] == 'array':
                                    prop_loc = request_body['content'][encoding_type]['schema']['properties'][property_name]
                                    prop_loc.setdefault("items", {})
                                    if constraint_set.get("items") is not None and constraint_set.get("items").strip() != "None":
                                        prop_loc['items'].setdefault("type", constraint_set.get("items"))
                                    if constraint_set.get("format") is not None and constraint_set.get("format").strip() != "None":
                                        prop_loc['items'].setdefault("format", constraint_set.get("format"))
                                else:
                                    request_body['content'][encoding_type]['schema']['properties'][property_name].setdefault("type", constraint_set.get("type"))
                                constraint_set.pop("type")
                            for field in constraint_set:
                                request_body['content'][encoding_type]['schema']['properties'][property_name].setdefault(field, constraint_set.get(field))
                else: 
                    constraint_set = generated_request_body_values[0]
                    if 'name' in constraint_set:
                        constraint_set.pop("name")
                    if 'examples' in constraint_set:
                        request_body['content'][encoding_type].setdefault("examples", {})
                        for key in constraint_set['examples']['examples']:
                            request_body['content'][encoding_type]['examples'][key] = constraint_set['examples']['examples'][key]
                        constraint_set.pop("examples")
                    if 'x-dependencies' in constraint_set:
                        xdependencies.extend(constraint_set['x-dependencies'])
                        constraint_set.pop("x-dependencies")
                    if 'type' in constraint_set:
                        if constraint_set['type'] == 'array':
                            schema_loc = request_body['content'][encoding_type]['schema']
                            schema_loc.setdefault("items", {})
                            if constraint_set.get("items") is not None and constraint_set.get("items") != "None":
                                schema_loc['items'].setdefault("type", constraint_set.get("items"))
                            if constraint_set.get("format") is not None and constraint_set.get("format") != "None":
                                schema_loc['items'].setdefault("format", constraint_set.get("format"))
                        else:
                            request_body['content'][encoding_type]['schema'].setdefault("type", constraint_set.get("type"))
                        constraint_set.pop("type")
                    for field in constraint_set:
                        request_body['content'][encoding_type]['schema'].setdefault(field, constraint_set.get(field))

    def model_constraints(self, path, method):
        constraint_dict =  run_llm_chain(self.read_path, path, method)
        parameters = {}
        request_body = []
        for parameter in constraint_dict:
            parameter_spec = {}
            parameter_spec['name'] = parameter['name']
            self._add_parameter_constraint(parameter_spec, self.parameter_constraint_parser.parse(parameter["parameter_constraints"]))
            self._add_ipd_constraint(parameter_spec, self.ipd_parser.parse_parameter(parameter["operational_constraints"]))
            self._add_parameter_type_values(parameter_spec, self.parameter_format_parser.parse(parameter["parameter_formats"]))
            if parameter["name"] in self.method_parameter_set[self._convert_key((path,method))]:
                self._add_example_values(parameter_spec, self.example_parser.parse_examples(parameter["parameter_examples"], is_requestBody=False, parameter_name=parameter["name"]))
                parameters[parameter["name"]] = parameter_spec
            else: 
                self._add_example_values(parameter_spec, self.example_parser.parse_examples(parameter["parameter_examples"], is_requestBody=False, parameter_name=parameter["name"]))
                request_body.append(parameter_spec)
        return parameters, request_body

    def make_report_constraint_object(self, path, operation, parameter, values, requestBody):
        restrictions = []
        for value, restrict in values.items():
            restrictions.append({
                "restriction_name": value,
                "restriction_value": restrict
            })
        # save navigation to parameter to edit in RevolvingParser
        return {
            "path": path,
            "method": operation,
            "parameter": parameter,
            "restrictions": restrictions,
            "request_body": requestBody
        }

    def find_report_constraints(self, report_values):
        constraint_list = []
        for path, method in report_values.items():
            for operation, parameters in method.items():
                for parameter, values in parameters.items():
                    if parameter != "request-body":
                        constraint_list.append(
                            self.make_report_constraint_object(path, operation, parameter, values, False))
                    else:
                        for request_parameter, request_values in values.items():
                            constraint_list.append(
                                self.make_report_constraint_object(path, operation, request_parameter, request_values,
                                                                   True))
        return constraint_list

    def add_properties_with_report(self, constraint, parameter_properties, parameter_level, is_requestBody):
        special_properties = {"items", "x-dependencies", "examples", "properties"} # requires special parsing
        check_consistency = {"collectionFormat", "format", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"} # check if they coincide with the correct type

        # check for type constraint first to ensure consistency checks
        for restriction in constraint["restrictions"]:
            if restriction["restriction_name"] == "type":
                parameter_properties["type"] = restriction["restriction_value"]

        for restriction in constraint["restrictions"]:
            name = restriction["restriction_name"]
            value = restriction["restriction_value"]

            # add if standard property
            if name not in special_properties and name not in check_consistency:
                parameter_properties.setdefault(name, value)

            elif name in check_consistency:
                # check for array-only properties
                if name == "collectionFormat" or name == "minItems" or name == "maxItems":
                    if parameter_properties["type"] == "array":
                        parameter_properties.setdefault(name, value)
                # check for integer-only properties
                elif name == "minimum" or name == "maximum":
                    if parameter_properties["type"] == "integer" or parameter_properties["type"] == "number":
                        parameter_properties.setdefault(name, value)
                # check for string-only properties
                elif name == "format" or name == "minLength" or name == "maxLength":
                    if parameter_properties["type"] == "string":
                        parameter_properties.setdefault(name, value)

            elif name in special_properties:

                # x-dependencies occur outside "parameters"
                if name == "x-dependencies":
                    parameter_level.setdefault(name, [])
                    for dependency in value: # given as a list
                        parameter_level[name].extend(value)

                # examples occur within "parameters" but no in the specific parameter
                elif name == "examples":
                    examples = []
                    for example in value["provided"]:
                        if example != "None":
                            examples.append(example)
                    for example in value["generated"]:
                        if example != "None":
                            examples.append(example)

                    parameter_properties.setdefault("examples", {})
                    for i in range(len(examples)):
                        parameter_properties[name][f"example{i}"] = {
                            "value": examples[i]
                        }

                elif name == "items":
                    parameter_properties.setdefault(name, {})
                    parameter_properties[name].setdefault("type", value)

                elif name == "properties":
                    parameter_properties.setdefault(name, {})
                    parameter_properties[name].setdefault(constraint["parameter"], {})
                    for property_name, property_value in value.items():
                        parameter_properties[name][constraint["parameter"]].setdefault(property_name, property_value)

    def change_specification_with_report(self, constraint_list):
        for constraint in constraint_list:
            if not constraint["request_body"]:
                parameter_level = self.output_builder['paths'][constraint["path"]][constraint["method"]]
                # parameter_level stores as list
                for parameter in parameter_level['parameters']:
                    if parameter["name"] == constraint["parameter"]:
                        self.add_properties_with_report(constraint, parameter["schema"], parameter_level, False)
            else:
                for application, schema in self.output_builder['paths'][constraint["path"]][constraint["method"]]["requestBody"]["content"].items():
                    if application != 'description':
                        property_level = schema['schema']
                        # property_level stores as object
                        # some request bodies don't have "properties" and only have one parameter
                        if "properties" not in property_level:
                            self.add_properties_with_report(constraint, property_level, property_level, True)
                        else:
                            parameter_properties = property_level['properties'][constraint["parameter"]]
                            self.add_properties_with_report(constraint, parameter_properties, property_level, True)

    def build_specification_with_report(self, file_path):
        print("Attempting generation at: " + file_path)
        with open(file_path, 'r') as json_file:
            report_values = json.load(json_file)

        # IDEA: make a list of constraint objects with the path and the added constraints that we listed in the report,
        # then navigate to that location in the SpecificationBuilder and copy them over
        constraint_list = self.find_report_constraints(report_values)

        # we can now attempt to add the constraints to the specification
        self.change_specification_with_report(constraint_list)

        # choose if we are outputting in JSON or YAML
        self.create_output_file()

    def build_specification(self): # this runs the specification builder using the llm
        for path, method in self.paths:
            self.process_operation(path, method)
        self.create_output_file()

    def create_output_file(self):
        if not os.path.exists(os.path.dirname(self.output_path)):
            os.makedirs(os.path.dirname(self.output_path))
        if self.output_path.split(".")[-1] == 'yaml':
            with open(self.output_path, 'w') as yaml_file:
                yaml.dump(self.output_builder, yaml_file, default_flow_style=False, sort_keys=False)
        elif self.output_path.split(".")[-1] == 'json':
            with open(self.output_path, 'w') as json_file:
                json.dump(self.output_builder, json_file, indent=4, sort_keys=False)