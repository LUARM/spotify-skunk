
#!/bin/bash

# Set bash options
set -e -x

# Load environment variables from .env file
if [ -f .env ]; then
   export $(cat .env | xargs)
fi

# Define the name of the zip file
ZIP_FILE="lambda_function.zip"

# Function ARN from environment variable
FUNCTION_ARN=$FUNCTION_ARN

# Check if FUNCTION_ARN is set
if [ -z "$FUNCTION_ARN" ]
then
      echo "ERROR: FUNCTION_ARN environment variable is not set."
      exit 1
fi

rm -f $ZIP_FILE
zip -r $ZIP_FILE *.py html/

# Append the contents of the 'dependencies' directory at the root of the zip file
if [ -d "dependencies" ]; then
    (cd dependencies && zip -rg ../$ZIP_FILE .)
fi

# Updating the Lambda function
aws lambda update-function-code --function-name $FUNCTION_ARN --zip-file fileb://$ZIP_FILE
aws lambda wait function-updated --function-name $FUNCTION_ARN

# Check if TEST_SNIPPET is set and file exists
if [ -n "$TEST_SNIPPET" ] && [ -f "$TEST_SNIPPET" ]; then
    # Invoke the Lambda function using the contents of TEST_SNIPPET
    aws lambda invoke --function-name $FUNCTION_ARN --payload file://$TEST_SNIPPET output.json
    cat output.json |jq 
fi