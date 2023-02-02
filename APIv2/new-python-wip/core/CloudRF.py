#!/usr/bin/env python3

# This file is not meant to be called directly. It should be imported.
if __name__ != '__main__':
    import argparse
    import csv
    import datetime
    import json
    import os
    import requests
    import stat
    import sys
    import textwrap
    import urllib3

    from .ArgparseCustomFormatter import ArgparseCustomFormatter
    from .PythonValidator import PythonValidator

class CloudRF:
    allowedOutputTypes = []
    calledFromPath = None
    description = 'CloudRF'
    requestType = None

    URL_GITHUB = 'https://github.com/Cloud-RF/CloudRF-API-clients'

    def __init__(self, REQUEST_TYPE, ALLOWED_OUTPUT_TYPES, DESCRIPTION, CURRENT_PATH):
        self.allowedOutputTypes = ALLOWED_OUTPUT_TYPES
        # Where was the script called from?
        self.calledFromPath = CURRENT_PATH
        self.description = DESCRIPTION
        self.requestType = REQUEST_TYPE

        PythonValidator.version()

        self.__argparseInitialiser()

        # If we are in verbose mode then just output everything
        if self.__arguments.verbose:
            self.__parser.print_help()
            print()

        if not self.__arguments.strict_ssl:
            self.__verboseLog('Strict SSL disabled.')
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.__validateRequestType()
        self.__validateApiKey()
        self.__validateFileAndDirectoryPermissions()
        self.__jsonTemplate = self.__validateJsonTemplate()
        self.__csvInputList = self.__validateCsv()

        if self.__arguments.input_csv and self.__csvInputList:
            # CSV has been used, run a request for each of the CSV rows
            for row in self.__csvInputList:
                # Adjust the input JSON template to meet the values which are found in the CSV row
                newJsonData = self.__customiseJsonFromCsvRow(templateJson = self.__jsonTemplate, csvRowDictionary = row)

                self.__calculate(jsonData = newJsonData)
        else:
            # Just run a calculation based on the template
            self.__calculate(jsonData = self.__jsonTemplate)

        sys.exit('Process completed. Please check your output folder (%s)' % self.__arguments.output_directory)

    def __argparseInitialiser(self):
        self.__parser = argparse.ArgumentParser(
            description = textwrap.dedent(self.description),
            formatter_class = ArgparseCustomFormatter,
            epilog = 'For more details about this script please consult the GitHub documentation at %s.' % self.URL_GITHUB
        )

        outputPath = str(self.calledFromPath).rstrip('/') + '/output'

        self.__parser.add_argument('-t', '--input-template', dest = 'input_template', required = True, help = 'Absolute path to input JSON template used as part of the calculation.')
        self.__parser.add_argument('-i', '--input-csv', dest = 'input_csv', help = 'Absolute path to input CSV, used in combination with --input-template to customise your template to a specific usecase. The CSV header row must be included. Header row values must be defined in dot notation format of the template key that they are to override in the template, for example transmitter latitude will be named as "transmitter.lat".')
        self.__parser.add_argument('-k', '--api-key', dest = 'api_key', required = True, help = 'Your API key to the CloudRF API service.')
        self.__parser.add_argument('-u', '--base-url', dest = 'base_url', default = 'https://api.cloudrf.com/', help = 'The base URL for the CloudRF API service.')
        self.__parser.add_argument('--no-strict-ssl', dest = 'strict_ssl', action="store_false", default = True, help = 'Do not verify the SSL certificate to the CloudRF API service.')
        self.__parser.add_argument('-r', '--save-raw-response', dest = 'save_raw_response', default = False, action = 'store_true', help = 'Save the raw response from the CloudRF API service. This is saved to the --output-directory value.')
        self.__parser.add_argument('-o', '--output-directory', dest = 'output_directory', default = outputPath, help = 'Absolute directory path of where outputs are saved.')
        self.__parser.add_argument('-s', '--output-file-type', dest = 'output_file_type', choices = ['all'] + self.allowedOutputTypes, help = 'Type of file to be downloaded.', default = 'kmz')
        self.__parser.add_argument('-v', '--verbose', action="store_true", default = False, help = 'Output more information on screen. This is often useful when debugging.')

        self.__arguments = self.__parser.parse_args()

    def __calculate(self, jsonData):
        now = datetime.datetime.now()
        requestName = now.strftime('%Y%m%d%H%M%S_' + now.strftime('%f')[:3])
        saveBasePath = str(self.__arguments.output_directory).rstrip('/') + '/' + requestName

        self.__verboseLog('Running %s calculation: %s' % (self.requestType, requestName))

        try:
            response = requests.post(
                url = str(self.__arguments.base_url).rstrip('/') + '/' + self.requestType,
                headers = {
                    'key': self.__arguments.api_key
                },
                json = jsonData,
                verify = self.__arguments.strict_ssl
            )

            self.__checkHttpResponse(httpStatusCode = response.status_code, httpRawResponse = response.text)

            if self.__arguments.verbose:
                print(response.text)

        except requests.exceptions.SSLError:
            sys.exit('SSL error occurred. This is common with self-signed certificates. You can try disabling SSL verification with --no-strict-ssl.')

    def __checkHttpResponse(self, httpStatusCode, httpRawResponse):
        if httpStatusCode != 200:
            print('An HTTP %d error occurred with your request. Full response from the CloudRF API is listed below.' % httpStatusCode)
            print(httpRawResponse)

            if httpStatusCode == 400:
                sys.exit('HTTP 400 refers to a bad request. You likely have bad values in your input JSON/CSV. For good examples please consult %s' % self.URL_GITHUB)
            elif httpStatusCode == 401:
                sys.exit('HTTP 401 refers to an unauthorised request. Your API key is likely incorrect.')
            elif httpStatusCode == 403:
                sys.exit('HTTP 403 refers to a forbidden request. Your API key appears to be correct but you do not appear to have permission to make your request.')
            elif httpStatusCode == 500:
                sys.exit('HTTP 500 refers to an issue with the server. A problem with the CloudRF API service appears to have occurred.')
            else:
                sys.exit('An unknown HTTP error has occured. Please consult the above response from the CloudRF API, or %s' % self.URL_GITHUB)

    def __customiseJsonFromCsvRow(self, templateJson, csvRowDictionary):
        for key, value in csvRowDictionary.items():
            # We are using dot notation so split out on this
            parts = str(key).split('.')

            # Should be a maxium of 2 parts so we can just be explicit here and update the template JSON
            if len(parts) == 2:
                templateJson[parts[0]][parts[1]] = value
            elif len(parts) == 1:
                templateJson[key] = value
            else:
                sys.exit('Maximum depth of dot notation 2. Please check your input CSV.')
        
        return templateJson

    def __validateApiKey(self):
        parts = str(self.__arguments.api_key).split('-')
        externalPrompt = 'Please make sure that you are using the correct key from https://cloudrf.com/my-account'

        if len(parts) != 2:
            sys.exit('Your API key appears to be in the incorrect format. %s' % externalPrompt)

        if not parts[0].isnumeric():
            sys.exit('Your API key UID component (part before "-") appears to be incorrect. %s' % externalPrompt)

        if len(parts[1]) != 40:
            sys.exit('Your API key token component (part after "-") appears to be incorrect. %s' % externalPrompt)

    def __validateCsv(self):
        if self.__arguments.input_csv:
            try:
                returnList = []

                with open(self.__arguments.input_csv, 'r') as csvInputFile:
                    reader = csv.DictReader(csvInputFile)

                    for row in reader:
                        for key, value in row.items():
                            if not key or not value:
                                raise AttributeError('There is an empty header or value in the input CSV file (%s)' % self.__arguments.input_csv)
                            
                            # We are using dot notation, a header should never be more than 2 deep
                            parts = str(key).split('.')

                            if len(parts) > 2:
                                raise AttributeError('Maximum depth of dot notation is 2. You have a value with a depth of %d in the input CSV file (%s)' % (len(parts), self.__arguments.input_csv))

                        returnList.append(row)
                        
                return returnList
            except PermissionError:
                sys.exit('Permission error when trying to read input CSV file (%s)' % self.__arguments.input_csv)
            except AttributeError as e:
                sys.exit(e)
            except:
                sys.exit('An unknown error occurred when checking input CSV file (%s)' % (self.__arguments.input_csv))

    def __validateFileAndDirectoryPermissions(self):
        if not os.path.exists(self.__arguments.input_template):
            sys.exit('Your input template JSON file (%s) could not be found. Please check your path. Please note that this should be in absolute path format.' % self.__arguments.input_template)
        else:
            self.__verboseLog('Input template JSON file (%s) found with file permissions: %s' % (self.__arguments.input_template, oct(stat.S_IMODE(os.lstat(self.__arguments.input_template).st_mode))))

        if self.__arguments.input_csv:
            if not os.path.exists(self.__arguments.input_csv):
                sys.exit('Your input CSV file (%s) could not be found. Please check your path. Please note that this should be in absolute path format.' % self.__arguments.input_csv)
            else:
                self.__verboseLog('Input CSV file (%s) found with file permissions: %s' % (self.__arguments.input_csv, oct(stat.S_IMODE(os.lstat(self.__arguments.input_csv).st_mode))))
        else:
            print('Input CSV has not been specified. Default values in input template JSON file will be used.')

        if not os.path.exists(self.__arguments.output_directory):
            self.__verboseLog('Output directory (%s) does not exist, attempting to create.' % self.__arguments.output_directory)
            os.makedirs(self.__arguments.output_directory)
            self.__verboseLog('Output directory (%s) created successfully.' % self.__arguments.output_directory)

        self.__verboseLog('Output directory (%s) exists with permissions: %s' % (self.__arguments.output_directory, oct(stat.S_IMODE(os.lstat(self.__arguments.output_directory).st_mode))))

        try:
            # Check if any file can be written to the output directory
            testFilePath = str(self.__arguments.output_directory).rstrip('/') + '/tmp'
            open(testFilePath, 'a')
            os.remove(testFilePath)
        except PermissionError:
            sys.exit('Unable to create files in output directory (%s)' % self.__arguments.output_directory)

    def __validateJsonTemplate(self):
        try:
            with open(self.__arguments.input_template, 'r') as jsonTemplateFile:
                return json.load(jsonTemplateFile)
        except PermissionError:
            sys.exit('Permission error when trying to read input template JSON file (%s)' % self.__arguments.input_template)
        except json.decoder.JSONDecodeError:
            sys.exit('Input template JSON file (%s) is not a valid JSON file.' % self.__arguments.input_template)
        except:
            sys.exit('An unknown error occurred when checking input template JSON file (%s)' % (self.__arguments.input_template))

    def __validateRequestType(self):
        allowedRequestTypes = ['area']

        if self.requestType and self.requestType in allowedRequestTypes:
            self.__verboseLog('Valid request type of %s being used.' % self.requestType)
        else:
            sys.exit('Unsupported request type of %s being used. Allowed request types are: %s' % (self.requestType, allowedRequestTypes))

    def __verboseLog(self, message):
        if self.__arguments.verbose:
            print(message)

if __name__ == '__main__':
    sys.exit('This is a core file and should not be executed directly. Please see %s for more details.' % CloudRF.URL_GITHUB)